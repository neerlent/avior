import asyncio
import functools
import logging
import serial
from functools import wraps
from serial_asyncio import create_serial_connection
from threading import RLock

_LOGGER = logging.getLogger(__name__)
EOL = b'\r'
LEN_EOL = len(EOL)
TIMEOUT = 2  # Number of seconds before serial operation timeout
BAUDRATE = 19200


class Avior(object):
    """
    Avior HDMI Matrix Switch interface
    """

    def set_zone_source(self, zone: int, source: int):
        """
        Set source for zone
        :param zone: Zone 1-4
        :param source: integer from 1-4
        """
        raise NotImplementedError()

    def set_all_zone_source(self, source: int):
        """
        Set source for all zones
        :param source: integer from 1-4
        """
        raise NotImplementedError()

    def read(self):
        """View information from the device.  May not work on this device."""
        raise NotImplementedError()

    def set_echo(self, on: bool):
        """If the Echo feature is enabled: for each action from the front
        panel (pushbuttons) or IR interface, the VM0404H sends a corresponding
        acknowledgement message to the attached controller or management
        device via the RS-232 port."""
        raise NotImplementedError()

    def set_power_on_detection(self, on: bool):
        """Enabling Power On Detection means that the Avior automatically
        switches to the next powered on device when one of the HDMI source
        devices is powered off. """
        raise NotImplementedError()

    def set_mute(self, zone: int, on: bool):
        """Enable or disable audio coming from the output port"""
        raise NotImplementedError()

    def set_cec(self, zone: int, on: bool):
        """Consumer Electronics Control (CEC) allows interconnected HDMI
        devices to communicate and respond to one remote control. """
        raise NotImplementedError()

    def set_button_enable(self, on: bool):
        """enable or disable the front panel pushbuttons"""
        raise NotImplementedError()

    def set_edid_mode(self, mode: str):
        """Extended Display Identification Data (EDID) is a data format that
        contains a display's basic information and is used to communicate with
        the video source/system. """
        raise NotImplementedError()

    def reset(self):
        """reset the device back to the default factory settings"""
        raise NotImplementedError()


# Helpers
# all supported AVIOR switch commands
# Switch Port Command
#   sw i01 o03  //  input 1 to ouptut 3
#   sw o03 off  //  turn off output 3
#   sw o02 +    //  select next input for output 2
def _format_set_zone_source(zone: int, source: int) -> bytes:
    """Set the input source for one output zone"""
    source = int(max(1, min(source, 4)))
    zone = int(max(1, min(zone, 4)))
    cmdstring = 'sw i0{0} o0{1}\r\n'.format(source, zone).encode()
    return cmdstring


def _format_set_all_zone_source(source: int) -> bytes:
    """Set the input source for all output zones"""
    source = int(max(1, min(source, 4)))
    cmdstring = 'sw i0{0} o*\r\n'.format(source).encode()
    return cmdstring


# Read Command
#   read
def _format_read() -> bytes:
    """View information from the device.  May not work on this device."""
    return 'read\r\n'.encode()


# Echo Command
#   echo on
#   echo off
def _format_echo(on: bool) -> bytes:
    """If the Echo feature is enabled: for each action from the front panel
    (pushbuttons) or IR interface, the VM0404H sends a corresponding
    acknowledgement message to the attached controller or management device
    via the RS-232 port."""
    mode = 'on' if on else 'off'
    cmdstring = 'echo {}\r\n'.format(mode).encode()
    return cmdstring


# Power On Detection Command
#   pod on
#   pod off
def _format_power_on_detection(on: bool) -> bytes:
    """Enabling Power On Detection means that the VM0404H automatically
    switches to the next powered on device when one of the HDMI source devices
    is powered off. """
    mode = 'on' if on else 'off'
    cmdstring = 'pod {}\r\n'.format(mode).encode()
    return cmdstring


# Mute Command
#   mute o03 off
#   mute o02 on
def _format_mute(zone: int, on: bool) -> bytes:
    """Enable or disable audio coming from the output port"""
    mode = 'on' if on else 'off'
    cmdstring = 'mute o{0} {1}\r\n'.format(zone, mode).encode()
    return cmdstring


# CEC Command
#   cec o01 on
#   cec o04 off
def _format_cec(zone: int, on: bool) -> bytes:
    """Consumer Electronics Control (CEC) allows interconnected HDMI devices
    to communicate and respond to one remote control. """
    mode = 'on' if on else 'off'
    cmdstring = 'cec o{0} {1}\r\n'.format(zone, mode).encode()
    return cmdstring


# Panel Button Control Command
#   button on
def _format_button(on: bool) -> bytes:
    """enable or disable the front panel pushbuttons"""
    mode = 'on' if on else 'off'
    cmdstring = 'button {}\r\n'.format(mode).encode()
    return cmdstring


# EDID Command
#   edid port1
#   edid remix
#   edid default
def _format_edid(mode: str) -> bytes:
    """Extended Display Identification Data (EDID) is a data format that
    contains a display's basic information and is used to communicate with
    the video source/system. """
    if mode not in ['port1', 'remix', 'default']:
        mode = 'default'
    cmdstring = 'edid {}\r\n'.format(mode).encode()
    return cmdstring


# Reset Command
#   reset
def _format_reset() -> bytes:
    """reset the device back to the default factory settings"""
    return 'reset\r\n'.encode()


def get_avior(url):
    """
    Return synchronous version of Avior interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: synchronous implementation of Avior interface
    """
    lock = RLock()
    # print(serial)

    def synchronized(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper

    class AviorSync(Avior):
        def __init__(self, url):
            """
            Initialize the client.
            """
            self._port = serial.serial_for_url(url, do_not_open=True)
            self._port.baudrate = BAUDRATE
            self._port.stopbits = serial.STOPBITS_ONE
            self._port.bytesize = serial.EIGHTBITS
            self._port.parity = serial.PARITY_NONE
            self._port.timeout = TIMEOUT
            self._port.write_timeout = TIMEOUT
            self._port.open()

        def _process_request(self, request: bytes, skip=0):
            """
            Send data to socket
            :param request: request that is sent to the Avior
            :param skip: # of bytes to skip for end of transmission decoding
            :return: ascii string returned by Avior
            """
            _LOGGER.debug('Sending "%s"', request)

            # clear
            self._port.reset_output_buffer()
            self._port.reset_input_buffer()
            # send
            self._port.write(request)
            self._port.flush()
            # receive
            result = bytearray()
            while True:
                c = self._port.read(1)
                if c is None:
                    break
                if not c:
                    raise serial.SerialTimeoutException(
                        'Connection timed out! Last received bytes {}'
                        .format([hex(a) for a in result]))
                result += c
                if len(result) > skip and result[-LEN_EOL:] == EOL:
                    break
            ret = bytes(result)
            _LOGGER.debug('Received "%s"', ret)
            return ret.decode('ascii')

        @synchronized
        def set_zone_source(self, zone: int, source: int):
            # Set zone source
            return self._process_request(_format_set_zone_source(zone, source))

        @synchronized
        def set_all_zone_source(self, source: int):
            # Set all zones to one source
            return self._process_request(_format_set_all_zone_source(source))

        @synchronized
        def read(self):
            """View information from the device.  Currently broken."""
            print(self._process_request(_format_read()))

        @synchronized
        def set_echo(self, on: bool):
            """If the Echo feature is enabled: for each action from the front
            panel (pushbuttons) or IR interface, the Avior sends a
            corresponding acknowledgement message to the attached controller
            or management device via the RS-232 port."""
            self._process_request(_format_echo(on))

        @synchronized
        def set_power_on_detection(self, on: bool):
            """Enabling Power On Detection means that the Avior automatically
            switches to the next powered on device when one of the HDMI source
            devices is powered off. """
            self._process_request(_format_power_on_detection(on))

        @synchronized
        def set_mute(self, zone: int, on: bool):
            """Enable or disable audio coming from the output port"""
            self._process_request(_format_mute(zone, on))

        @synchronized
        def set_cec(self, zone: int, on: bool):
            """Consumer Electronics Control (CEC) allows interconnected HDMI
            devices to communicate and respond to one remote control. """
            self._process_request(_format_cec(zone, on))

        @synchronized
        def set_button_enable(self, on: bool):
            """enable or disable the front panel pushbuttons"""
            self._process_request(_format_button(on))

        @synchronized
        def set_edid_mode(self, mode: str):
            """Extended Display Identification Data (EDID) is a data format
            that contains a display's basic information and is used to
            communicate with the video source/system. """
            return self._process_request(_format_edid(mode))

        @synchronized
        def reset(self):
            """reset the device back to the default factory settings"""
            self._process_request(_format_reset())

    return AviorSync(url)


@asyncio.coroutine
def get_async_avior(port_url, loop):
    """
    Return asynchronous version of Avior interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of Avior interface
    """

    lock = asyncio.Lock()

    def locked_coro(coro):
        @asyncio.coroutine
        @wraps(coro)
        def wrapper(*args, **kwargs):
            with (yield from lock):
                return (yield from coro(*args, **kwargs))
        return wrapper

    class AviorAsync(Avior):
        def __init__(self, avior_protocol):
            self._protocol = avior_protocol

        @locked_coro
        @asyncio.coroutine
        def set_zone_source(self, zone: int, source: int):
            yield from self._protocol.send(_format_set_zone_source(zone, source))

        @locked_coro
        @asyncio.coroutine
        def set_all_zone_source(self, source: int):
            yield from self._protocol.send(_format_set_all_zone_source(source))

        @locked_coro
        @asyncio.coroutine
        def read(self):
            """View information from the device.  Currently broken."""
            print(self._protocol.send(_format_read()))

        @locked_coro
        @asyncio.coroutine
        def set_echo(self, on: bool):
            """If the Echo feature is enabled: for each action from the front
            panel (pushbuttons) or IR interface, the VM0404H sends a
            corresponding acknowledgement message to the attached controller
            or management device via the RS-232 port."""
            yield from self._protocol.send(_format_echo(on))

        @locked_coro
        @asyncio.coroutine
        def set_power_on_detection(self, on: bool):
            """Enabling Power On Detection means that the Avior automatically
            switches to the next powered on device when one of the HDMI source
            devices is powered off. """
            yield from self._protocol.send(_format_power_on_detection(on))

        @locked_coro
        @asyncio.coroutine
        def set_mute(self, zone: int, on: bool):
            """Enable or disable audio coming from the output port"""
            yield from self._protocol.send(_format_mute(zone, on))

        @locked_coro
        @asyncio.coroutine
        def set_cec(self, zone: int, on: bool):
            """Consumer Electronics Control (CEC) allows interconnected HDMI
            devices to communicate and respond to one remote control. """
            yield from self._protocol.send(_format_cec(zone, on))

        @locked_coro
        @asyncio.coroutine
        def set_button_enable(self, on: bool):
            """enable or disable the front panel pushbuttons"""
            yield from self._protocol.send(_format_button(on))

        @locked_coro
        @asyncio.coroutine
        def set_edid_mode(self, mode: str):
            """Extended Display Identification Data (EDID) is a data format
            that contains a display's basic information and is used to
            communicate with the video source/system. """
            yield from self._protocol.send(_format_edid(mode))

        @locked_coro
        @asyncio.coroutine
        def reset(self):
            """reset the device back to the default factory settings"""
            yield from self._protocol.send(_format_reset())

    class AviorProtocol(asyncio.Protocol):
        def __init__(self, loop):
            super().__init__()
            self._loop = loop
            self._lock = asyncio.Lock()
            self._transport = None
            self._connected = asyncio.Event(loop=loop)
            self.q = asyncio.Queue(loop=loop)

        def connection_made(self, transport):
            self._transport = transport
            self._connected.set()
            _LOGGER.debug('port opened %s', self._transport)

        def data_received(self, data):
            asyncio.ensure_future(self.q.put(data), loop=self._loop)

        @asyncio.coroutine
        def send(self, request: bytes, skip=0):
            yield from self._connected.wait()
            result = bytearray()
            # Only one transaction at a time
            with (yield from self._lock):
                self._transport.serial.reset_output_buffer()
                self._transport.serial.reset_input_buffer()
                while not self.q.empty():
                    self.q.get_nowait()
                self._transport.write(request)
                try:
                    while True:
                        result += yield from asyncio.wait_for(self.q.get(), TIMEOUT, loop=self._loop)
                        if len(result) > skip and result[-LEN_EOL:] == EOL:
                            ret = bytes(result)
                            _LOGGER.debug('Received "%s"', ret)
                            return ret.decode('ascii')
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout during receiving response for command '%s', received='%s'", request, result)
                    raise

    _, protocol = yield from create_serial_connection(loop, functools.partial(AviorProtocol, loop), port_url, baudrate=BAUDRATE)

    return AviorAsync(protocol)