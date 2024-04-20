#!/usr/bin/env python
"""
Digital INPUT/OUTPUT integration component for Arduino

See: http://linuxcnc.org/docs/html/hal/halmodule.html

To install dependencies:
    python2 -m pip install pyserial
    python2 -m pip install pyudev
"""
from __future__ import print_function
import sys
import platform

PYTHON_REQUIRED_VERSION = 2
PYTHON_MAJOR_VERSION = sys.version_info[0]

# ==== CONSTANTS ===================
WARMUP_READS = 25  # We will read from the device this many times to let flow-control establish itself before trying
                  # to process the message "for real"
CPU_SLEEP_SECONDS = 0.001  # this provides time back to the CPU, no reason to run as fast as possible.
BAUD_RATE = 9600  # BAUD_RATE must match the mega2560 programmed rate.
                  # The parameter baudrate can be one of the standard values:
                  #  50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200.
                  #  These are well supported on all platforms.

CONFIGURATION_NAME = 'mega2560_hal_io_config.json'  # the configuration file will be loaded from the same directory
                                                    # as this script.
INITIALIZE_WAIT_SECONDS = 1.0  # Pause for a few seconds to ensure the mega is given time to initialize
REPORT_INTERVAL_SECONDS = 10.0  # You will only see the pin status report if logging is set to INFO
INPUT_MSG_PREFIX = 2  # tells us how many bytes are at the start of input messages before input states begin.
INPUT_MSG_SUFFIX = 1
PIN_OFF = chr(1)  # these constants are set in the microcontroller
PIN_ON = chr(100)
CHECKSUM_ON = 3
CHECKSUM_OFF = 2
DEFAULT_BIT_PIN_STATE = False  # default state is OFF
SERIAL_OPTIONS = {
    'xonxoff': False,  # software flow-control, both `xonxoff` and `rtscts` cannot be enabled.
    'rtscts': True,  # hardware flow control RTS/CTS (available on Linux)
    'dsrdtr': None,  # setting this to None will mean it follows the `rtscts` setting
    'timeout': 1,
    'write_timeout': 2,
}

if sys.version_info[0] != PYTHON_REQUIRED_VERSION:
    raise RuntimeError('Invalid python version! ({})\n' \
        'LinuxCNC is currently only compatible with Python {} \n' \
        'When LinuxCNC 2.9 is officially released it will support Python 3'.format(PYTHON_MAJOR_VERSION,
                                                                                   PYTHON_REQUIRED_VERSION))

from os.path import join, dirname
import json
import time
import logging
import logging.handlers
logging.basicConfig()
try:
    import serial
except ImportError as e:
    raise ImportError('"pyserial" is not available, install with "python -m pip install pyserial" - {}'.format(e))
import serial.tools.list_ports
from serial.serialutil import SerialException, \
    PortNotOpenError, SerialTimeoutException, Timeout


class DeviceNotFound(NameError):
    pass


class HalShim:
    """
    Provides a fake shim for hal, offers basic functionality and validation.
    """
    HAL_BIT = 1
    HAL_IN = 2
    HAL_OUT = 3

    def __init__(self, name):
        self._name = name
        self._vals = {}
        self._pins = {}
        self._log = logging.getLogger(name)

    @property
    def log(self):
        return self._log

    def __getitem__(self, pin_name):
        self.log.debug('get -> {}.{}={}'.format(self._name, pin_name, self._vals.get(pin_name)))
        return self._vals[pin_name]

    def __setitem__(self, pin_name, value):
        if pin_name not in self._pins:
            raise KeyError('invalid pin name: {}'.format(pin_name))

        self.log.debug('set -> {}.{}={}'.format(self._name, pin_name, self._vals.get(pin_name)))
        self._vals[pin_name] = value

    def newpin(self, pin_name, data_type, direction):
        self._pins[pin_name] = (data_type, direction)
        self._vals[pin_name] = None

    @staticmethod
    def component(name):
        return HalShim(name)

    @staticmethod
    def component_exists(name):
        return False


# === READ CONFIGURATION ===========
conf_path = join(dirname(__file__), CONFIGURATION_NAME)
try:
    conf_fp = open(conf_path, mode='r')
except IOError as e:
    raise IOError('unable to open file {}, - {}'.format(conf_path, e))

try:
    conf = json.load(conf_fp)
except json.DecodeError as e:
    raise json.DecoderError('error reading program configuration, invalid json: {}, - {}'.format(conf_path, e))

# === CONFIG VALUES ================
COMPONENT = conf['COMPONENT']  # this is the prefix the pin name will start with.
INPUT_COUNT = conf['INPUT_COUNT']  # pin-number that pins will start at, usually 0 or 1
OUTPUT_COUNT = conf['OUTPUT_COUNT']  # the number of outputs the device supports and is configured for
DEVICE_DESCRIPTION = conf['DEVICE_DESCRIPTION'] # the device description via USB - we will connect to this USB device.
DEVICE_SERIAL = conf['DEVICE_SERIAL']  # (optional) if multiple devices are connected, you can specify the serial number of the device to
                                       # connect to, to disambiguate them from eachother.
LOG_LEVEL = conf['LOG_LEVEL']
log = logging.getLogger(COMPONENT)
log.setLevel(logging.INFO)

try:
    import hal
    handler = logging.handlers.SysLogHandler(address='/dev/log')
    log.addHandler(handler)
    log.setLevel(getattr(logging, LOG_LEVEL))
except ImportError:
    # if HAL isn't available we will provide a simple shim
    # so the program  can be verified.
    log.warning('hal unavailable, providing shim layer for debugging')
    hal = HalShim

if not isinstance(INPUT_COUNT, int):
    raise ValueError('INPUT_COUNT invalid')
if not isinstance(OUTPUT_COUNT, int):
    raise ValueError('OUTPUT_COUNT invalid')

INPUT_NAMES = {}  # map HARDWARE PIN NUMBER (0 BASED) to tuple (Software pin name, Software pin name not)
OUTPUT_NAMES = {}  # map HARDWARE PIN NUMBER (0 BASED) to tuple (Software pin name, Software pin name not)

# ================================================
# === CONFIGURE HAL COMPONENT ====================
# ================================================
io = hal.component(COMPONENT)

# setup input pins
for i in range(INPUT_COUNT):
    # pin names are "component-input-00"
    #               "component-input-00-not"
    name = 'input-{:02d}'.format(i)
    not_name = 'input-{:02d}-not'.format(i)  # configure an inverse pin - this makes it use to test for NOT
    io.newpin(name, hal.HAL_BIT, hal.HAL_OUT)
    io.newpin(not_name, hal.HAL_BIT, hal.HAL_OUT)

    INPUT_NAMES[i] = (name, not_name)


# setup output pins
for i in range(OUTPUT_COUNT):
    name = 'output-{:02d}'.format(i)
    io.newpin(name, hal.HAL_BIT, hal.HAL_IN)

    OUTPUT_NAMES[i] = name

# very important
io.ready()
log.debug('hal component {} is ready'.format(COMPONENT))


def discover_port():
    """discover the serial port name where the arduino device is located"""
    if platform.system() == 'Windows':
        return discover_port_serial()
    else:
        return discover_port_udev()


def discover_port_serial():
    serial_port = None
    devices = []
    ports = list(serial.tools.list_ports.comports())
    for port in ports:

        devices.append('{}, {}'.format(port.name, port.description))
        if port.description is not None and DEVICE_DESCRIPTION not in port.description:
            continue
        if DEVICE_SERIAL is not None and DEVICE_SERIAL != port.serial:
            continue
        serial_port = port.name

    if not serial_port:
        raise DeviceNotFound('USB Device not found, DESCRIPTION: {}, SERIAL: {}\n' \
            'AVAILABLE DEVICES:\n{}'.format(DEVICE_DESCRIPTION, DEVICE_SERIAL, '\n'.join(devices)))

    return serial_port


def discover_port_udev():
    """
    On linux pyserial will not be able to list usb tty devices.

    The Arduino will present itself to pyudev like so:
    {u'DEVLINKS': u'/dev/serial/by-path/pci-0000:00:14.0-usb-0:9:1.0 /dev/serial/by-id/usb-Arduino__www.arduino.cc__0042_75935313636351605211-if00',
     u'DEVNAME': u'/dev/ttyACM0',
     u'DEVPATH': u'/devices/pci0000:00/0000:00:14.0/usb1/1-9/1-9:1.0/tty/ttyACM0',
     u'ID_BUS': u'usb',
     u'ID_MODEL': u'0042',
     u'ID_MODEL_ENC': u'0042',
     u'ID_MODEL_FROM_DATABASE': u'Mega 2560 R3 (CDC ACM)',
     u'ID_MODEL_ID': u'0042',
     u'ID_PATH': u'pci-0000:00:14.0-usb-0:9:1.0',
     u'ID_PATH_TAG': u'pci-0000_00_14_0-usb-0_9_1_0',
     u'ID_PCI_CLASS_FROM_DATABASE': u'Serial bus controller',
     u'ID_PCI_INTERFACE_FROM_DATABASE': u'XHCI',
     u'ID_PCI_SUBCLASS_FROM_DATABASE': u'USB controller',
     u'ID_REVISION': u'0001',
     u'ID_SERIAL': u'Arduino__www.arduino.cc__0042_75935313636351605211',
     u'ID_SERIAL_SHORT': u'75935313636351605211',
     u'ID_TYPE': u'generic',
     u'ID_USB_CLASS_FROM_DATABASE': u'Communications',
     u'ID_USB_DRIVER': u'cdc_acm',
     u'ID_USB_INTERFACES': u':020201:0a0000:',
     u'ID_USB_INTERFACE_NUM': u'00',
     u'ID_VENDOR': u'Arduino__www.arduino.cc_',
     u'ID_VENDOR_ENC': u'Arduino\\x20\\x28www.arduino.cc\\x29',
     u'ID_VENDOR_FROM_DATABASE': u'Arduino SA',
     u'ID_VENDOR_ID': u'2341',
     u'MAJOR': u'166',
     u'MINOR': u'0',
     u'SUBSYSTEM': u'tty',
     u'TAGS': u':systemd:',
     u'USEC_INITIALIZED': u'761122913'}

    Note that the ability to list device information varies from chipset to chipset.
    The most reliable way to identify a device is by serial number.
    """
    try:
        import pyudev
    except ImportError as e:
        raise ImportError('pyudev not available, install with "python -m pip install pyudev" - {}'.format(e))

    context = pyudev.Context()
    devices = []
    serial_port = None
    # note that you MUST ask for a specific context otherwise you won't get pertinant usb information
    # the subsystem below is REQUIRED
    for device in context.list_devices(subsystem='tty', ID_BUS='usb'):
        for value in device.values():
            if DEVICE_DESCRIPTION is not None and DEVICE_DESCRIPTION in value:
                serial_port = device['DEVNAME']
                continue

            if DEVICE_SERIAL is not None and DEVICE_SERIAL in value:
                serial_port = device['DEVNAME']
                continue

            devices.append('{}, MODEL: {}, SERIAL: {}'.format(device['DEVNAME'],
                                                              device['ID_MODEL_FROM_DATABASE'],
                                                              device['ID_SERIAL_SHORT']))

    if not serial_port:
        raise DeviceNotFound('USB Device not found, DESCRIPTION: {}, SERIAL: {}\n' \
            'AVAILABLE DEVICES:\n{}'.format(DEVICE_DESCRIPTION, DEVICE_SERIAL, '\n'.join(devices)))
    return serial_port


# =============================================
# ==== MAIN LOOP ==============================
# =============================================
tlast = time.time()
start_time = time.time()
warmup_counter = WARMUP_READS
in_counter = 0
out_counter = 0
arduino = None
while 1:

    # =============================================
    # ==== CONNECT TO ARDUINO DEVICE ==============
    # =============================================
    if arduino is None:
        serial_port = discover_port() # if the device isn't found, an exception will be raised here
        if not serial_port:
            raise ValueError('no valid serial port found')

        log.warning('connecting to Arduino at: "{}"'.format(serial_port))
        try:

            arduino = serial.Serial(port=serial_port,
                                    baudrate=BAUD_RATE,
                                    **SERIAL_OPTIONS)
            if not arduino.is_open:
                raise RuntimeError('port "{}" is not open after opening !?!?!'.format(serial_port))

            # read the first message and throw it away, it will usually be part of a message.
            arduino.readline()
        except Exception as e:
            log.exception('failed to connect to device at "{}" - {}'.format(serial_port, e))
            time.sleep(1)
            continue

    # Before beginning to read give time for the Arduino to initialize
    # it's important you don't BLOCK (time.sleep) during this period as it will cause connection issues
    if time.time() < (start_time + INITIALIZE_WAIT_SECONDS):
        time.sleep(CPU_SLEEP_SECONDS)
        continue

    # =============================================
    # ==== HANDLE INPUTS FROM DEVICE ==============
    # =============================================
    input_error = False
    try:
        input_msg = arduino.readline()
    except Exception:
        arduino = None
        log.exception('failed to read input from device')
        continue

    if warmup_counter > 0:
        warmup_counter -= 1
        time.sleep(CPU_SLEEP_SECONDS)
        continue

    expected_msg_length = INPUT_MSG_PREFIX + INPUT_COUNT + INPUT_MSG_SUFFIX
    if len(input_msg) < expected_msg_length:
        log.warning('invalid msg length: {}, expected: {}'.format(len(input_msg), expected_msg_length))
        continue

    checksum = ord(input_msg[0])  # the device sends a checksum based on what inputs are on
    num_inputs = ord(input_msg[1])  # the device sends with the input msg the number of configured inputs

    try:
        input_states = input_msg[INPUT_MSG_PREFIX:-INPUT_MSG_SUFFIX]
    except IndexError:
        log.warning('bad input msg, {}')
        input_error = True
        input_states = []

    # the device reports to us how many hardware inputs are configured in its current programming
    # this should match what we expect via configuration, if it doesn't there is a problem.
    if num_inputs != INPUT_COUNT:
        log.warning('the configured inputs, and the number supported by the device do not match! %s != %s' % (INPUT_COUNT, num_inputs))
        input_error = True

    calc_pins_on = sum([1 if char_value == PIN_ON else 0 for char_value in input_states])
    calc_checksum = sum([CHECKSUM_ON if char_value == PIN_ON else CHECKSUM_OFF for char_value in input_states])

    # ensure the input checksum is sane
    if checksum != calc_checksum:
        log.warning('bad checksum: (microcontroller) %s != (calculated) %s' % (checksum, calc_checksum))
        input_error = True

    inputs_msg_length = len(input_states)
    if inputs_msg_length != INPUT_COUNT:
        log.warning('input states msg wrong length, expected: {}, got: {}'.format(INPUT_COUNT, inputs_msg_length))
        input_error = True

    if not input_error:
        in_counter += 1
        for i in range(INPUT_COUNT):
            # ord() will convert a single byte to an integer
            # the status of the port are represented with a 1 byte integer or (char)
            byte_pos = i
            state = input_states[byte_pos]
            input_name, input_not_name = INPUT_NAMES[i]
            # set the pin state based upon the input state the device provided
            if state == PIN_ON:
                io[input_name] = True
                io[input_not_name] = False
            elif state == PIN_OFF:
                io[input_name] = False
                io[input_not_name] = True
            else:
                log.warning('non binary pin state from controller: {}'.format(ord(state)))
                io[input_name] = DEFAULT_BIT_PIN_STATE
                io[input_not_name] = not DEFAULT_BIT_PIN_STATE
    else:
        input_states = '\0'

    # =============================================
    # ==== SEND OUTPUTS TO DEVICE =================
    # =============================================

    # create empty array of output states, we must update outputs
    # each iteration regardless if they've changed.
    # the device has an internal timeout, if it doesn't hear from us in a given time it will disable all
    # outputs.
    output_states = [chr(0)] * OUTPUT_COUNT
    for i in range(OUTPUT_COUNT):
        output_name = OUTPUT_NAMES[i]
        # set the state of the arduino pin based no the current state of the HAL pin
        output_states[i] = chr(int(bool(io[output_name])))

    # output_bin is our binary message containing output states sent to the controller
    # create a binary string, each character being a 1 byte integer for pin status, terminated with newline [(char) 10]
    output_bin = ''.join(output_states) + '\n'
    try:
        # write the state of each output to the device.
        arduino.write(output_bin)
    except SerialTimeoutException as e:
        log.warning(str(e))
        arduino.reset_output_buffer()  # throw away anything we sent to the arduino.
    except Exception:
        log.exception('failed to write to device')
        arduino = None
        continue
    else:
        out_counter += 1
        log.debug('update success')

    time.sleep(CPU_SLEEP_SECONDS)

    # periodically report on inputs and outputs
    if (time.time() - tlast) >= REPORT_INTERVAL_SECONDS:
        msgs_sec = float(sum((in_counter, out_counter))) / REPORT_INTERVAL_SECONDS
        log.info('msg/sec {} - input msgs: {}, output msgs: {}'.format(msgs_sec, in_counter, out_counter))
        log.info('input:  {}'.format(''.join([str(ord(state)) for state in input_states])))
        log.info('output: {}'.format(''.join([str(ord(state)) for state in output_states])))
        # reset counters/timer
        tlast = time.time()
        in_counter = out_counter = 0
