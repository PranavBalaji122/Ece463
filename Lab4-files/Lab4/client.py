#
import time
import sys
import queue
from packet import Packet

class Client:
    """Client class"""

    def __init__(self, addr, sendFile, recvFile, MSS):
        """Inititalize parameters"""
        self.addr = addr
        self.sendFile = sendFile
        self.recvFile = recvFile
        self.MSS = MSS
        self.link = None
        self.linkChanges = queue.Queue()
        self.keepRunning = True
        self.f = open("logs/Client-"+self.addr+"-recvd-pkts.dump", "w")


    def changeLink(self, change):
        """Add a link to the client.
           The 'change' argument should be a tuple ('add', link).
        """
        self.linkChanges.put(change)


    def runClient(self):
        """Main loop of client"""
        while self.keepRunning:
            time.sleep(0.1)
            try:
                change = self.linkChanges.get_nowait()
                if change[0] == "add":
                    self.link = change[1]
            except queue.Empty:
                pass
            self.handleRecvdPackets()
            self.sendPackets()


    def handleRecvdPackets(self):
        """Handle packets recvd from the network.
           This method is called every 0.1 seconds.
        """
        pass


    def sendPackets(self):
        """Send packets into the network.
           This method is called every 0.1 seconds.
        """
        pass

