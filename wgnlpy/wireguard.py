#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from pyroute2 import netlink
from base64 import b64decode

class WireGuard(object):
    from .nlas import device as __device

    def __init__(self, **kwargs):
        self.__socket = netlink.generic.GenericNetlinkSocket()
        self.__socket.bind('wireguard', self.__device)

    def __get(self, device):
        flags = netlink.NLM_F_ACK | netlink.NLM_F_REQUEST | netlink.NLM_F_DUMP
        return self.__socket.nlm_request(device, msg_type=self.__socket.prid, msg_flags=flags)

    def __set(self, device):
        flags = netlink.NLM_F_ACK | netlink.NLM_F_REQUEST
        return self.__socket.nlm_request(device, msg_type=self.__socket.prid, msg_flags=flags)

    def get_interface(self, ifname, spill_private_key=False, spill_preshared_keys=False):
        device = self.__device.get_device()
        device['attrs'].append(('WGDEVICE_A_IFNAME', ifname))
        messages = self.__get(device)

        class WireGuardInfo(object):
            def __init__(self, messages, spill_private_key, spill_preshared_keys):
                self.ifindex = messages[0].get_attr('WGDEVICE_A_IFINDEX')
                self.ifname = messages[0].get_attr('WGDEVICE_A_IFNAME')
                if spill_private_key:
                    self.private_key = messages[0].get_attr('WGDEVICE_A_PRIVATE_KEY')
                    assert self.private_key is None or len(self.private_key) == 32
                self.public_key = messages[0].get_attr('WGDEVICE_A_PUBLIC_KEY')
                self.listen_port = messages[0].get_attr('WGDEVICE_A_LISTEN_PORT')
                self.fwmark = messages[0].get_attr('WGDEVICE_A_FWMARK')

                assert self.ifname == ifname
                assert self.public_key is None or len(self.public_key) == 32

                self.peers = { }

                for message in messages:
                    for peer in message.get_attr('WGDEVICE_A_PEERS') or []:
                        public_key = peer.get_attr('WGPEER_A_PUBLIC_KEY')
                        if public_key not in self.peers:
                            preshared_key = peer.get_attr('WGPEER_A_PRESHARED_KEY')
                            if not spill_preshared_keys:
                                preshared_key = preshared_key is not None and preshared_key != bytes(32)
                            else:
                                assert preshared_key is None or len(preshared_key) == 32
                            self.peers[public_key] = {
                                'preshared_key': preshared_key,
                                'last_handshake_time': peer.get_attr('WGPEER_A_LAST_HANDSHAKE_TIME'),
                                'persistent_keepalive_interval': peer.get_attr('WGPEER_A_PERSISTENT_KEEPALIVE_INTERVAL'),
                                'tx_bytes': peer.get_attr('WGPEER_A_TX_BYTES'),
                                'rx_bytes': peer.get_attr('WGPEER_A_RX_BYTES'),
                                'allowedips': [],
                                'protocol_version': peer.get_attr('WGPEER_A_PROTOCOL_VERSION'),
                            }
                        for allowedip in peer.get_attr('WGPEER_A_ALLOWEDIPS') or []:
                            self.peers[public_key]['allowedips'].append(allowedip.network())

            def __repr__(self):
                return repr({
                    'ifindex': self.ifindex,
                    'ifname': self.ifname,
                    'public_key': self.public_key,
                    'listen_port': self.listen_port,
                    'fwmark': self.fwmark,
                    'peers': self.peers,
                })

        return WireGuardInfo(messages, spill_private_key, spill_preshared_keys)

    def set_interface(self, ifname,
            private_key=None,
            listen_port=None,
            fwmark=None,
            replace_peers=False,
            ):

        device = self.__device.set_device()
        device['attrs'].append(('WGDEVICE_A_IFNAME', ifname))

        if replace_peers:
            device['attrs'].append(('WGDEVICE_A_FLAGS', device.flag.REPLACE_PEERS.value))

        if private_key is not None:
            assert len(private_key) == 32
            device['attrs'].append(('WGDEVICE_A_PRIVATE_KEY', private_key))

        if listen_port is not None:
            device['attrs'].append(('WGDEVICE_A_LISTEN_PORT', listen_port))

        if fwmark is not None:
            device['attrs'].append(('WGDEVICE_A_FWMARK', fwmark))

        return self.__set(device)

    def remove_peers(self, ifname, *public_keys):
        device = self.__device.set_device()
        device['attrs'].append(('WGDEVICE_A_IFNAME', ifname))
        device['attrs'].append(('WGDEVICE_A_PEERS', []))

        for public_key in public_keys:
            if not isinstance(public_key, (bytes, bytearray)):
                public_key = b64decode(public_key)

            peer = self.__device.peer()
            assert len(public_key) == 32
            peer['attrs'].append(('WGPEER_A_PUBLIC_KEY', public_key))
            peer['attrs'].append(('WGPEER_A_FLAGS', peer.flag.REMOVE_ME.value))
            device.get_attr('WGDEVICE_A_PEERS').append(peer)

        return self.__set(device)

    def set_peer(self, ifname, public_key,
            preshared_key=None,
            endpoint=None,
            persistent_keepalive_interval=None,
            allowedips=None,
            replace_allowedips=None,
            ):

        device = self.__device.set_device()
        device['attrs'].append(('WGDEVICE_A_IFNAME', ifname))

        if not isinstance(public_key, (bytes, bytearray)):
            public_key = b64decode(public_key)

        peer = device.peer()
        assert len(public_key) == 32
        peer['attrs'].append(('WGPEER_A_PUBLIC_KEY', public_key))

        if replace_allowedips is None and allowedips is not None:
            replace_allowedips = True

        if replace_allowedips:
            peer['attrs'].append(('WGPEER_A_FLAGS', peer.flag.REPLACE_ALLOWEDIPS.value))

        if preshared_key is not None:
            assert len(preshared_key) == 32
            peer['attrs'].append(('WGPEER_A_PRESHARED_KEY', preshared_key))

        if endpoint is not None:
            peer['attrs'].append(('WGPEER_A_ENDPOINT', self.__device.peer.sockaddr.frob(endpoint)))

        if persistent_keepalive_interval is not None:
            peer['attrs'].append(('WGPEER_A_PERSISTENT_KEEPALIVE_INTERVAL', persistent_keepalive_interval))

        if allowedips is not None:
            peer['attrs'].append(('WGPEER_A_ALLOWEDIPS', []))

            for allowedip in allowedips:
                peer.get_attr('WGPEER_A_ALLOWEDIPS').append(self.__device.peer.allowedip.frob(allowedip))

        device['attrs'].append(('WGDEVICE_A_PEERS', [peer]))
        return self.__set(device)

    def replace_allowedips(self, ifname, *public_keys):
        device = self.__device.set_device()
        device['attrs'].append(('WGDEVICE_A_IFNAME', ifname))
        device['attrs'].append(('WGDEVICE_A_PEERS', []))

        for public_key in public_keys:
            if not isinstance(public_key, (bytes, bytearray)):
                public_key = b64decode(public_key)

            peer = self.__device.peer()
            assert len(public_key) == 32
            peer['attrs'].append(('WGPEER_A_PUBLIC_KEY', public_key))
            peer['attrs'].append(('WGPEER_A_FLAGS', peer.flag.REPLACE_ALLOWEDIPS.value))
            device.get_attr('WGDEVICE_A_PEERS').append(peer)

        return self.__set(device)

#
