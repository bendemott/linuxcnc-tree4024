"""
Pendant Control IO for LinuxCNC

USB Integration driver for XHC-HB04 (4 axis pendant)
"""

import sys
import time
import usb.core
import ctypes

VENDOR_ID = 0x10ce
PRODUCT_ID = 0xeb93

AXS_BYTE = 5
AXS_MAP = {
    6: 'off',
    17: 'x',
    18: 'y',
    19: 'z',
    20: 'a',
}

SPD_BYTE = 4
SPD_MAP = {
    13: '2%',
    14: '5%',
    15: '10%',
    16: '30%',
    26: '60%',
    27: '100%',
    28: 'lead',
}
SPD_DEFAULT = 0.0

BTN_BYTE = 2
BTN2_BYTE = 3
BTN_MAP = {
    1: 'reset',
    2: 'stop',
    3: 'start',
    4: 'feed+',
    5: 'feed-',
    6: 'spindle+',
    7: 'spindle-',
    8: 'm_home',
    9: 'safe_z',
    10: 'w_home',
    11: 'spindle_toggle',
    12: 'fn_mode',
    13: 'probe_z',
    14: 'continuous',
    15: 'step',
}

# buttons available when NOT in function mode
MACRO_MAP = {
    1: 'reset',
    2: 'stop',
    3: 'start',
    4: 'macro1',
    5: 'macro2',
    6: 'macro3',
    7: 'macro4',
    8: 'macro5',
    9: 'macro6',
    10: 'macro7',
    11: 'macro8',
    13: 'macro9',
    16: 'macro10',
    12: 'fn_mode',
    14: 'continuous',
    15: 'step',
}

ENC_BYTE = 6

AXIS_KEY = 'axis'
SPEED_KEY = 'speed'
MPG_KEY = 'mpg'


def main(argv=None):
    while True:
        print('\r... searching for pendant', end='')
        pendant = find_device()
        if pendant is None:
            time.sleep(1)
            continue

        pendant.set_configuration()
        cfg = pendant.get_active_configuration()
        interface = cfg[(0,0)]
        endpoint = interface[0]

        mpg_count = 0
        fn_mode = True
        while True:
            try:
                data = get_data(device=pendant, endpoint=endpoint, timeout=100)
                if data is None:
                    continue
                buttons = read_data(data, fn_mode, mpg_count)
            except Exception as e:
                raise
                print('read failure', e)
                time.sleep(1)
                break

            mpg_count = buttons.get('mpg', mpg_count)
            fn_mode = buttons.get('fn_mode', fn_mode)

            for name in sorted(buttons):
                print(name, buttons[name])


def get_data(device, endpoint, timeout=500):

    try:
        data = device.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize, timeout=timeout)
    except usb.core.USBError as e:
        return None

    return data


def read_data(data, fn_mode=False, mpg_count=0):
    """
    Returns the sate of all buttons as a dictionary

    :param data: raw data read from the device
    :param fn_mode: True/False the state of the toggle 'function-mode' determines if a macro is returned or a regular button
    :param mpg_count: If you would like the MPG count to be added to or removed from include this
    :return:
    """
    btns = {key: False for key in (list(BTN_MAP.values()) + list(MACRO_MAP.values()))}

    axs = AXS_MAP.get(data[AXS_BYTE], data[AXS_BYTE])
    btns[AXIS_KEY] = axs

    spd = SPD_MAP.get(data[SPD_BYTE], data[SPD_BYTE])
    btns[SPEED_KEY] = spd

    # two buttons can be pressed at the same time
    btn_code = data[BTN_BYTE]
    btn2_code = data[BTN2_BYTE]
    active_btns = set((btn_code, btn2_code))

    if fn_mode:
        for code, btn_name in BTN_MAP.items():
            btns[btn_name] = code in active_btns

    else:
        for code, btn_name in MACRO_MAP.items():
            btns[btn_name] = code in active_btns

    mpg_val = data[ENC_BYTE]
    if mpg_val > 127:
        mpg_count = mpg_count + (256 - mpg_val) * -1
    else:
        mpg_count = mpg_count + mpg_val

    btns[MPG_KEY] = mpg_count
    btns['release'] = btn_code == 0
    return btns


class Whb04b_struct(ctypes.Structure):
    buff_old = 'buff_old'
    _fields_ = [
                   #/* header of our packet */
                   ("header", ctypes.c_uint16, ),
                   ("seed", ctypes.c_uint8),
                   ("flags", ctypes.c_uint8),
                   #/* work pos */
                   ("x_wc_int", ctypes.c_uint16),
                   ("x_wc_frac", ctypes.c_uint16),
                   ("y_wc_int", ctypes.c_uint16),
                   ("y_wc_frac", ctypes.c_uint16),
                   ("z_wc_int", ctypes.c_uint16),
                   ("z_wc_frac", ctypes.c_uint16),
                   #/* speed */
                   ("feedrate", ctypes.c_uint16),
                   ("sspeed", ctypes.c_uint16),
                   ("padding", ctypes.c_uint8 * 8) ]


def update_display(device):
    """
struct whb03_out_data
{
   /* header of our packet */
   uint16_t   magic;
   /* day of the month .. funny i know*/
   uint8_t      day;
   /* work pos */
   uint16_t   x_wc_int;
   uint8_t      x_wc_frac;
   uint16_t   y_wc_int;
   uint8_t      y_wc_frac;
   uint16_t   z_wc_int;
   uint8_t      z_wc_frac;
   /* machine pos */
   uint16_t   x_mc_int;
   uint8_t      x_mc_frac;
   uint16_t   y_mc_int;
   uint8_t      y_mc_frac;
   uint16_t   z_mc_int;
   uint8_t      z_mc_frac;

   /* speed */
   uint16_t   feedrate_ovr;
   uint16_t   sspeed_ovr;
   uint16_t   feedrate;
   uint16_t   sspeed;

   uint8_t    step_mul;
   uint8_t    state;

};
    :param x:
    :param y:
    :param z:
    :return:
    """
    p = Whb04b_struct()
    data = None
    showRotary = False
    data_old = 0
    pendant_is_on = False

    p.header = 0xFDFE
    p.seed = 0xFE
    p.flags = 0x01
    p.x_wc_int = 100
    p.x_wc_frace = 2000
    p.y_wc_int = 200
    p.y_wc_frace = 1000
    p.z_wc_int = 300
    p.z_wc_frace = 3000
    p.feedrate = 16
    p.sspeed = 3600

    buff = ctypes.cast(ctypes.byref(p), ctypes.POINTER(ctypes.c_char * ctypes.sizeof(p)))
    if buff.contents.raw != p.buff_old and pendant_is_on:
        # print " ".join(hex(ord(c)) for c in buff.contents.raw)
        device.ctrl_transfer(0x21, 0x09, 0x306, 0x00, chr(0x06) + buff.contents.raw[0:7])
        device.ctrl_transfer(0x21, 0x09, 0x306, 0x00, chr(0x06) + buff.contents.raw[7:14])
        device.ctrl_transfer(0x21, 0x09, 0x306, 0x00, chr(0x06) + buff.contents.raw[14:21])
        # dev.ctrl_transfer(0x21, 0x09, 0x306, 0x00, chr(0x06) + buff.contents.raw[21:28])
        # dev.ctrl_transfer(0x21, 0x09, 0x306, 0x00, chr(0x06) + buff.contents.raw[28:35])
        p.buff_old = buff.contents.raw


def find_device():
    return usb.core.find(idProduct=PRODUCT_ID)


if __name__ == '__main__':
    sys.exit(main(sys.argv))