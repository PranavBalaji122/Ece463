#
import sys
import threading
import json
import pickle
import signal
import time
import os.path
import queue
from collections import defaultdict
from client import Client
from link import Link
from router import Router

class Network:
    """Network class maintains all clients, routers, links, and confguration"""

    def __init__(self, netJsonFilepath, routerClass):
        """Create a new network from the parameters in the file at 'netJsonFilepath'.
           'routerClass' determines whether to use DVrouter, LSrouter, or the default Router.
        """

        # parse configuration details
        netJsonFile = open(netJsonFilepath, 'r')
        netJson = json.load(netJsonFile)
        self.latencyMultiplier = 100
        self.heartbeatTime = netJson["heartbeatTime"] * self.latencyMultiplier
        self.endTime = netJson["endTime"] * self.latencyMultiplier
        self.clientSendRate = netJson["clientSendRate"]*self.latencyMultiplier
        self.infinity = netJson["infinity"]

        # parse and create routers, clients, and links
        self.routers = self.parserouters(netJson["routers"], routerClass)
        self.clients = self.parseClients(netJson["clients"], self.clientSendRate)
        self.links = self.parseLinks(netJson["links"])

        # parse link changes
        if "changes" in netJson:
            self.changes = self.parseChanges(netJson["changes"])
        else:
            self.changes = None

        # parse correct routes and create some tracking fields
        self.threads = []
        self.routes = {}
        self.correctRoutes = self.parseCorrectRoutes(netJson["correctRoutes"])
        self.routesLock = threading.Lock()
        netJsonFile.close()


    def parserouters(self, routerParams, routerClass):
        """Parse routers from 'routerParams' dict"""
        routers = {}
        for addr in routerParams:
            if sys.argv[2] == "DV":
                routers[addr] = routerClass(addr, self.heartbeatTime, self.infinity)
            else:
                routers[addr] = routerClass(addr, self.heartbeatTime)
        return routers


    def parseClients(self, clientParams, clientSendRate):
        """Parse clients from 'clientParams' dict"""
        clients = {}
        for addr in clientParams:
            clients[addr] = Client(addr, clientParams, clientSendRate, self.updateRoute)
        return clients


    def parseLinks(self, linkParams):
        """Parse links from 'linkParams' dict"""
        links = {}
        for addr1, addr2, p1, p2, c in linkParams:
            link = Link(addr1, addr2, c, self.latencyMultiplier)
            links[(addr1,addr2)] = (p1, p2, c, link)
        return links


    def parseChanges(self, changesParams):
        """Parse link changes from 'changesParams' dict"""
        changes = queue.PriorityQueue()
        for change in changesParams:
            changes.put(change)
        return changes


    def parseCorrectRoutes(self, routesParams):
        """Parse correct routes from 'routesParams' dict"""
        correctRoutes = defaultdict(list)
        for route in routesParams:
            src, dst = route[0], route[-1]
            correctRoutes[(src,dst)].append(route)
            self.routes[(src,dst)] = ([], False, -1)
        return correctRoutes


    def run(self):
        """Run the network. Start threads for each client and router.
           Start thread to track link changes.
           Wait until end time and then print the final output.
        """
        for router in self.routers.values():
            thread = router_thread(router)
            thread.start()
            self.threads.append(thread)
        for client in self.clients.values():
            thread = client_thread(client)
            thread.start()
            self.threads.append(thread)
        self.addLinks()
        if self.changes:
            self.handleChangesThread = handle_changes_thread(self)
            self.handleChangesThread.start()
        signal.signal(signal.SIGINT, self.handleInterrupt)
        time.sleep(self.endTime/float(1000))
        self.finalRoutes()
        sys.stdout.write("\nRoutes taken by last batch of packets between each pair of clients:")
        sys.stdout.write("\n"+self.getRouteString()+"\n")
        self.joinAll()


    def addLinks(self):
        """Add links to clients and routers"""
        for addr1, addr2 in self.links:
            p1, p2, c, link = self.links[(addr1, addr2)]
            if addr1 in self.clients:
                self.clients[addr1].changeLink(("add", link))
            if addr2 in self.clients:
                self.clients[addr2].changeLink(("add", link))
            if addr1 in self.routers:
                self.routers[addr1].changeLink(("add", p1, addr2, link, c))
            if addr2 in self.routers:
                self.routers[addr2].changeLink(("add", p2, addr1, link, c))


    def handleChanges(self):
        """Handle changes to links. Run this method in a separate thread.
           Uses a priority queue to track time of next change.
        """
        startTime = time.time()*1000
        while not self.changes.empty():
            changeTime, target, change = self.changes.get()
            currentTime = time.time()*1000
            waitTime = (changeTime*self.latencyMultiplier + startTime) - currentTime
            if waitTime > 0:
                time.sleep(waitTime/float(1000))
            # link changes
            if change == "up":
                addr1, addr2, p1, p2, c = target
                link = Link(addr1, addr2, c, self.latencyMultiplier)
                self.links[(addr1,addr2)] = (p1, p2, c, link)
                self.routers[addr1].changeLink(("add", p1, addr2, link, c))
                self.routers[addr2].changeLink(("add", p2, addr1, link, c))
            elif change == "down":
                addr1, addr2, = target
                p1, p2, _, link = self.links[(addr1, addr2)]
                self.routers[addr1].changeLink(("remove", p1))
                self.routers[addr2].changeLink(("remove", p2))


    def updateRoute(self, src, dst, route, seqNum):
        """Callback function used by clients to update the current routes taken by DATA packets"""
        self.routesLock.acquire()
        isGood = False
        if (src,dst) not in self.correctRoutes:
            isGood = False
        else:
            isGood = route in self.correctRoutes[(src,dst)]
        self.routes[(src,dst)] = (route, isGood, seqNum)
        self.routesLock.release()


    def logQueuedPackets(self):
        for addr1,addr2 in self.links:
            _, _, _, link = self.links[(addr1,addr2)]
            link.endtimereached = 1
            while not link.q12.empty():
                packet = link.q12.get_nowait()
                self.routes[(packet.srcAddr,packet.dstAddr)] = (packet.route, False, packet.content)
            while not link.q21.empty():
                packet = link.q21.get_nowait()
                self.routes[(packet.srcAddr,packet.dstAddr)] = (packet.route, False, packet.content)


    def getRouteString(self, labelIncorrect=True):
        """Create a string with all the current routes found by DATA packets and whether they are correct"""
        self.routesLock.acquire()
        self.logQueuedPackets()
        routeStrings = []
        allCorrect = True
        for src,dst in self.routes:
            route, isGood, _ = self.routes[(src,dst)]
            routeStrings.append("Packet({} -> {}): {} {}".format(src, dst, route,
                "" if (isGood or not labelIncorrect) else "Incorrect Route"))
            if not isGood:
                allCorrect = False
        routeStrings.sort()
        if allCorrect and len(self.routes) > 0:
            routeStrings.append("\nSUCCESS: All routes are correct!\n")
        else:
            routeStrings.append("\nFAILURE: Not all routes are correct!\n")
        routeString = "\n".join(routeStrings)
        self.routesLock.release()
        return routeString


    def getRoutePickle(self):
        """Create a pickle with the current routes found by DATA packets"""
        self.routesLock.acquire()
        routePickle = pickle.dumps(self.routes)
        self.routesLock.release()
        return routePickle


    def clearQueues(self):
        for addr1,addr2 in self.links:
            _, _, _, link = self.links[(addr1,addr2)]
            link.endtimereached = 1
            while not link.q12.empty():
                link.q12.get_nowait()
            while not link.q21.empty():
                link.q21.get_nowait()


    def finalRoutes(self):
        """Have the clients send one final batch of DATA packets"""
        self.clearQueues()
        for client in self.clients.values():
            client.lastSend()
        time.sleep(30)


    def joinAll(self):
        if self.changes:
            self.handleChangesThread.join()
        for thread in self.threads:
            thread.join()


    def handleInterrupt(self, signum, _):
        self.joinAll()
        quit()


def main():
    """Main function parses command line arguments and runs network"""
    if len(sys.argv) < 2:
        sys.stdout.write("Usage: python network.py [networkSimulationFile.json] [DV|LS]\n")
        return
    netCfgFilepath = sys.argv[1]
    routerClass = Router
    if len(sys.argv) >= 3:
        if sys.argv[2] == "DV":
            from DVrouter import DVrouter
            routerClass = DVrouter
        elif sys.argv[2] == "LS":
            from LSrouter import LSrouter
            routerClass = LSrouter
    net = Network(netCfgFilepath, routerClass)
    net.run()
    return

# Extensions of threading.Thread class

class router_thread(threading.Thread):

    def __init__(self, router):
        threading.Thread.__init__(self)
        self.router = router

    def run(self):
        self.router.runRouter()

    def join(self, timeout=None):
        self.router.keepRunning = False
        super(router_thread, self).join(timeout)

class client_thread(threading.Thread):

    def __init__(self, client):
        threading.Thread.__init__(self)
        self.client = client

    def run(self):
        self.client.runClient()

    def join(self, timeout=None):
        self.client.keepRunning = False
        super(client_thread, self).join(timeout)

class handle_changes_thread(threading.Thread):

    def __init__(self, network):
        threading.Thread.__init__(self)
        self.network = network

    def run(self):
        self.network.handleChanges()


if __name__ == "__main__":
    main()
    
