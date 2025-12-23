#
import time
import sys
import queue
from client import Client
from packet import Packet


class MyClient(Client):
    """Implement a reliable transport using selective acknowledgments."""

    def __init__(self, addr, sendFile, recvFile, MSS):
        """Client A is sending bytes from file 'sendFile' to client B.
           Client B stores the received bytes from A in file 'recvFile'.
        """
        # initialize superclass
        Client.__init__(self, addr, sendFile, recvFile, MSS)

        # Connection state
        self.connSetup = 0
        self.connEstablished = 0
        self.connTerminate = 0
        self.sendFile = sendFile
        self.recvFile = recvFile

        # -------------------------------
        # Sender state (Client A) – selective repeat with selective ACKs
        # -------------------------------
        self.base = 1                 # sequence number of the oldest unacknowledged packet
        self.next_seq_num = 1         # sequence number to use for the next new data packet
        self.window_size = 20         # sending window size
        self.unacked = {}             # seqNum -> {"packet": pkt, "time": send_time, "acked": bool}
        self.timeout_interval = 2.0   # retransmission timeout (seconds)
        self.eof = False              # True when we have read all bytes from sendFile
        self.fin_sent = False         # True once FIN has been sent

        # -------------------------------
        # Receiver state (Client B)
        # -------------------------------
        self.expected_seq = 1         # next in-order sequence number expected from A
        self.recv_buffer = {}         # seqNum -> payload (out-of-order buffer)

    # ----------------------------------------------------------------------
    # Receiving side (called every 0.1 seconds by the network)
    # ----------------------------------------------------------------------
    def handleRecvdPackets(self):
        """Handle packets recvd from the network.
           This method is called every 0.1 seconds.
        """
        if not self.link:
            return

        packet = self.link.recv(self.addr)  # receive a packet from the link
        if not packet:
            return

        # log recvd packet
        self.f.write(
            "Packet - srcAddr: " + packet.srcAddr +
            " dstAddr: " + packet.dstAddr +
            " seqNum: " + str(packet.seqNum) +
            " ackNum: " + str(packet.ackNum) +
            " SYNFlag: " + str(packet.synFlag) +
            " ACKFlag: " + str(packet.ackFlag) +
            " FINFlag: " + str(packet.finFlag) +
            " Payload: " + str(packet.payload)
        )
        self.f.write("\n")

        # --------------------------------------------------------------
        # Client A: sender of the file
        # --------------------------------------------------------------
        if self.addr == "A":
            # Connection setup complete: received SYN-ACK
            if packet.synFlag == 1 and packet.ackFlag == 1 and packet.finFlag == 0:
                # send final ACK of 3-way handshake
                ack_pkt = Packet("A", "B", 1, packet.seqNum + 1, 0, 1, 0, None)
                if self.link:
                    self.link.send(ack_pkt, self.addr)
                self.connEstablished = 1
                self.connSetup = 0
                return

            # Connection termination: received FIN-ACK from B
            if packet.finFlag == 1 and packet.ackFlag == 1:
                # send final ACK and let router end simulation
                ack_pkt = Packet("A", "B", 0, packet.seqNum + 1, 0, 1, 0, None)
                if self.link:
                    self.link.send(ack_pkt, self.addr)
                self.connTerminate = 0
                return

            # Data ACKs from B (selective ACK)
            if (
                packet.ackFlag == 1 and
                packet.synFlag == 0 and
                packet.finFlag == 0 and
                packet.payload is None
            ):
                ack_seq = packet.ackNum
                # Mark the corresponding packet as acknowledged
                if ack_seq in self.unacked:
                    self.unacked[ack_seq]["acked"] = True

                # Slide the sending window base forward
                while self.base in self.unacked and self.unacked[self.base]["acked"]:
                    del self.unacked[self.base]
                    self.base += 1

        # --------------------------------------------------------------
        # Client B: receiver of the file
        # --------------------------------------------------------------
        if self.addr == "B":
            # Received a SYN packet: start connection setup
            if packet.synFlag == 1 and packet.finFlag == 0 and packet.ackFlag == 0:
                syn_ack = Packet("B", "A", 0, packet.seqNum + 1, 1, 1, 0, None)
                if self.link:
                    self.link.send(syn_ack, self.addr)
                self.connSetup = 1
                return

            # Received a FIN packet from A: begin termination
            if packet.finFlag == 1 and packet.synFlag == 0 and packet.ackFlag == 1:
                fin_ack = Packet("B", "A", 0, packet.seqNum + 1, 0, 1, 1, None)
                if self.link:
                    self.link.send(fin_ack, self.addr)
                self.connTerminate = 1
                return

            # ACK for our SYN-ACK (final ACK of handshake)
            if (
                self.connSetup == 1 and
                packet.ackFlag == 1 and
                packet.synFlag == 0 and
                packet.finFlag == 0 and
                packet.payload is None
            ):
                self.connSetup = 0
                return

            # ACK for our FIN-ACK (final ACK of termination)
            if (
                self.connTerminate == 1 and
                packet.ackFlag == 1 and
                packet.synFlag == 0 and
                packet.finFlag == 0 and
                packet.payload is None
            ):
                self.connTerminate = 0
                return

            # Data packet from A (payload is not None, not SYN/FIN)
            if (
                packet.payload is not None and
                packet.synFlag == 0 and
                packet.finFlag == 0
            ):
                seq = packet.seqNum

                # Always send a selective ACK for the sequence number we received
                ack_pkt = Packet("B", "A", 0, seq, 0, 1, 0, None)
                if self.link:
                    self.link.send(ack_pkt, self.addr)

                # If this is a duplicate (already delivered), do not store again
                if seq < self.expected_seq:
                    return

                # Buffer out-of-order packet
                if seq not in self.recv_buffer:
                    self.recv_buffer[seq] = packet.payload

                # Deliver any newly in-order data
                while self.expected_seq in self.recv_buffer:
                    self.recvFile.write(self.recv_buffer[self.expected_seq])
                    del self.recv_buffer[self.expected_seq]
                    self.expected_seq += 1

    # ----------------------------------------------------------------------
    # Sending side (called every 0.1 seconds by the network)
    # ----------------------------------------------------------------------
    def sendPackets(self):
        """Send packets into the network.
           This method is called every 0.1 seconds.
        """
        # --------------------------------------------------------------
        # Client A: sender of the file
        # --------------------------------------------------------------
        if self.addr == "A":
            # Initiate connection setup with a SYN (once)
            if self.connSetup == 0 and self.connEstablished == 0:
                syn_pkt = Packet("A", "B", 0, 0, 1, 0, 0, None)
                if self.link:
                    self.link.send(syn_pkt, self.addr)
                self.connSetup = 1
                # Do not send data in the same tick as SYN
                return

            # Only send/recv data after connection established and before termination
            if self.connEstablished == 1 and self.connTerminate == 0:
                now = time.time()

                # 1. Retransmit any timed-out unacked data packets (selective repeat)
                for seq, info in list(self.unacked.items()):
                    if not info["acked"] and (now - info["time"] > self.timeout_interval):
                        if self.link:
                            self.link.send(info["packet"], self.addr)
                        info["time"] = time.time()

                # 2. Send new data packets while there is space in the window
                while (not self.eof) and (self.next_seq_num < self.base + self.window_size):
                    content = self.sendFile.read(self.MSS)
                    if not content:
                        # No more data to read from file
                        self.eof = True
                        break

                    data_pkt = Packet("A", "B", self.next_seq_num, 0, 0, 0, 0, content)
                    if self.link:
                        self.link.send(data_pkt, self.addr)

                    self.unacked[self.next_seq_num] = {
                        "packet": data_pkt,
                        "time": time.time(),
                        "acked": False,
                    }
                    self.next_seq_num += 1

                # 3. If we have reached EOF and all data is acked, send FIN
                if self.eof and (not self.unacked) and not self.fin_sent:
                    fin_pkt = Packet("A", "B", 0, 0, 0, 1, 1, None)
                    if self.link:
                        self.link.send(fin_pkt, self.addr)
                    self.fin_sent = True
                    self.connTerminate = 1

        # --------------------------------------------------------------
        # Client B: receiver of the file
        # --------------------------------------------------------------
        if self.addr == "B":
            # B only sends control/ACK packets from handleRecvdPackets.
            # Nothing to do here periodically.
            pass
