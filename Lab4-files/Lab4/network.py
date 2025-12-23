#
import sys
import threading
import json
import signal
import time
import os.path
import queue
import filecmp
from collections import defaultdict
from client import Client
from myClient import MyClient
from link import Link
from router import Router

class Network:
    """Network class maintains all clients, routers, links, and confgurations"""

    def __init__(self, netJsonFilepath, sendFile, recvFile, lossProb):
        """Create a new network from the parameters in the 'netJsonFilepath' file"""
        self.threads = []

        # parse configuration details
        netJsonFile = open(netJsonFilepath, 'r')
        netJson = json.load(netJsonFile)
        self.sendFile = sendFile
        self.recvFile = recvFile

        # parse and create routers, clients, and links
        self.routers = self.parserouters(netJson["routers"], lossProb)
        self.clients = self.parseClients(netJson["clients"], netJson["MSS"])
        self.links = self.parseLinks(netJson["links"], netJson["MSS"])

        netJsonFile.close()


    def parserouters(self, routerParams, lossProb):
        """Parse routers from 'routerParams' dict"""
        routers = {}
        for addr in routerParams:
            assert(addr == "1")
            routers[addr] = Router(addr, lossProb)
        return routers


    def parseClients(self, clientParams, MSS):
        """Parse clients from 'clientParams' dict"""
        clients = {}
        for addr in clientParams:
            assert(addr == "A" or addr == "B")
            if addr == "A":
                clients[addr] = MyClient(addr, self.sendFile, None, MSS)
            elif addr == "B":
                clients[addr] = MyClient(addr, None, self.recvFile, MSS)
        return clients


    def parseLinks(self, linkParams, MSS):
        """Parse links from 'linkParams' dict"""
        links = {}
        for addr1, addr2, p1, p2, c in linkParams:
            link = Link(addr1, addr2, c, MSS)
            links[(addr1,addr2)] = (p1, p2, c, link)
        return links


    def parseChanges(self, changesParams):
        """Parse link changes from 'changesParams' dict"""
        changes = queue.PriorityQueue()
        for change in changesParams:
            changes.put(change)
        return changes


    def run(self, f1, f2):
        """Run the network. Start threads for each client and router.
           Start thread to track link changes.
           Wait until end time and then print the final output.
        """
        start = time.time()
        for router in self.routers.values():
            thread = router_thread(router)
            thread.start()
            self.threads.append(thread)
        for client in self.clients.values():
            thread = client_thread(client)
            thread.start()
            self.threads.append(thread)
        self.addLinks()
        signal.signal(signal.SIGINT, self.handleInterrupt)
        while True:
            if self.routers["1"].endSimulation == 1:
                self.joinAll()
                end = time.time()
                print("\nTotal bytes sent = " + str(self.routers["1"].recvdByteCnt) + " bytes (" + str(self.routers["1"].recvdPktCnt) + " pkts)")
                print("Total time of transfer = " + str(round(end-start, 3)) + " seconds")
                self.sendFile.close()
                self.recvFile.close()
                time.sleep(1)
                result = filecmp.cmp(f1, f2, shallow=False)
                if result == True:
                    print("SUCCESS: Sent and received files match!")
                else:
                    print("FAILURE: Sent and received files do not match!")
                return
            else:
                time.sleep(5)


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


    def joinAll(self):
        for thread in self.threads:
            thread.join()


    def handleInterrupt(self, signum, _):
        self.joinAll()
        quit()


def main():
    """Main function parses command line arguments and runs the network"""
    if len(sys.argv) < 4:
        sys.stdout.write("Usage: python network.py [networkSimulationFile.json] [send file path] [recv file path] [loss probability]")
        return
    netCfgFilepath = sys.argv[1]
    f1 = sys.argv[2]
    f2 = sys.argv[3]
    lossProb = int(sys.argv[4])
    if lossProb < 0 or lossProb > 99:
        print("Error: Invalid loss probability value provided!")
        return
    sendFile = open(f1, 'r')
    recvFile = open(f2, 'w')
    net = Network(netCfgFilepath, sendFile, recvFile, lossProb)
    net.run(f1, f2)
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


if __name__ == "__main__":
    main()
    
