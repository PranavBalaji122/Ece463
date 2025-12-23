#
class Packet:
    """Packet class defines packets that clients and routers send/recv in the simulated network"""

    def __init__(self, srcAddr, dstAddr, seqNum, ackNum, synFlag, ackFlag, finFlag, payload=None):
        """create a new packet"""
        self.srcAddr = srcAddr  # address of the source of the packet
        self.dstAddr = dstAddr  # address of the destination of the packet
        self.seqNum = seqNum    # sequence number for reliability
        self.ackNum = ackNum    # acknowledgment number for reliability
        self.synFlag = synFlag  # SYN flag bit (set to 0 or 1)
        self.ackFlag = ackFlag  # ACK flag bit (set to 0 or 1)
        self.finFlag = finFlag  # FIN flag bit (set to 0 or 1)
        self.payload = payload  # payload of the packet (must be a string)
        ##----------------------
        self.time = None        # DO NOT TOUCH
        
