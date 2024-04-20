from __future__ import print_function

import math
import sys
import subprocess
from itertools import islice
import logging
import re
from pprint import pformat
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import hal
import gtk
import gobject


def chunk(it, size):
    """
    Given an iterator (sequence of numbers) this will generate an evenly distributed sequence of tuples
    of `size`

    >>> list(chunk(range(14), 3))
    [(0, 1, 2), (3, 4, 5), (6, 7, 8), (9, 10, 11), (12, 13)]

    :param it:
    :param size:
    :return:
    """
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


class EventBoxButton(gtk.EventBox):

    # see https://developer.gnome.org/pygtk/stable/class-gtkstyle.html
    BG_NORMAL_COLOR = 'black'
    BG_PRELIGHT_COLOR = 'white'
    BG_ACTIVE_COLOR = '#4dcf46'  # green

    FG_NORMAL_COLOR = 'white'
    FG_PRELIGHT_COLOR = 'black'
    FG_ACTIVE_COLOR = 'white'

    CURSOR_PRELIGHT = gtk.gdk.HAND2

    def __init__(self, widget=None, border=10):
        super(EventBoxButton, self).__init__()
        self.child_colors = {}

        if not widget:
            widget = gtk.Label()
            widget.modify_fg(gtk.STATE_NORMAL, gtk.gdk.color_parse(self.FG_NORMAL_COLOR))
            widget.set_padding(5, 8)

        self.add(widget)
        self.active = False
        self.set_border_width(border)
        self.set_can_focus(True)

        self.activate_normal_style()

        self.connect("button_press_event", self.on_press)
        self.connect("enter-notify-event", self.on_enter)
        self.connect("leave-notify-event", self.on_leave)

    def set_button_state(self, active=None):
        if active is not None:
            self.active = active
        fn = getattr(self, 'activate_active_style' if self.active else 'activate_normal_style')
        fn()

    def activate_normal_style(self):
        self.set_button_color(self.BG_NORMAL_COLOR)
        self.set_text_state('normal')

    def activate_prelight_style(self):
        self.set_button_color(self.BG_PRELIGHT_COLOR)
        self.set_text_state('prelight')

    def activate_active_style(self):
        self.set_button_color(self.BG_ACTIVE_COLOR)
        self.set_text_state('active')

    def set_text_state(self, state='normal'):
        default_color = getattr(self, 'FG_{}_COLOR'.format(state.upper()))
        for widget in self.get_children_recursive():
            if widget in self.child_colors:
                col = self.child_colors[widget]
                widget.get_style().copy()
                fn = getattr(widget, 'modify_{}'.format(col['attribute']))
                fn(gtk.STATE_NORMAL, gtk.gdk.color_parse(col.get(state, default_color)))

            elif isinstance(widget, gtk.Label):
                widget.modify_fg(gtk.STATE_NORMAL, gtk.gdk.color_parse(default_color))

    def set_button_color(self, color):
        style = self.get_style().copy()
        style.bg[gtk.STATE_NORMAL] = gtk.gdk.color_parse(color)
        self.set_style(style)

    def set_child_colors(self, child, attribute, normal, prelight, active):
        """
        Override colors for a particular child

        :param child:
        :param attribute: 'fg' or 'bg'
        :param normal: Normal color, "black"
        :param prelight: Hover color, "orange"
        :param active: Active color "blue"
        :return:
        """
        self.child_colors[child] = {'attribute': attribute,
                                    'normal': normal,
                                    'prelight': prelight,
                                    'active': active}

    def on_press(self, widget, event):
        self.set_button_state(not self.active)
        return True

    def on_enter(self, widget, event):
        widget.get_window().set_cursor(gtk.gdk.Cursor(self.CURSOR_PRELIGHT))
        self.activate_prelight_style()
        return True

    def on_leave(self, widget, event):
        widget.get_window().set_cursor(None)
        self.set_button_state()
        return True

    def get_children_recursive(self, widget=None):
        if widget is None:
            widget = self

        children = []

        if hasattr(widget, 'get_children'):
            for child in widget.get_children():
                children.append(child)
                child_iter = self.get_children_recursive(child)
                children.extend(child_iter)
        elif hasattr(widget, 'get_child') and widget.get_child() is not None:
            child = widget.get_child()
            children.append(child)
            child_iter = self.get_children_recursive(child)
            children.extend(child_iter)

        for child in children:
            yield child


class IOButton(EventBoxButton):
    pass


class InputButton(IOButton):
    """
    +------------------------------------
    | 03                       input
    |
    | SIGNAL NAME              extra
    """
    DEFAULT_SIZE = (250, 50)
    LIGHT_YELLOW = '#ffde21'
    LIGHTER_ORANGE = '#ffb62e'
    MEDIUM_ORANGE = '#f7b200'
    BRIGHT_ORANGE = '#ffb700'
    LIGHT_GREY1 = '#b8b8b8'
    LIGHT_GREY2 = '#b5b5b5'
    MED_GREY = '#525252'
    DARK_GREY = '#292929'
    DARK_GREY2 = '#212121'

    BG_NORMAL_COLOR = 'black'
    BG_PRELIGHT_COLOR = DARK_GREY2
    BG_ACTIVE_COLOR = MEDIUM_ORANGE

    FG_NORMAL_COLOR = MEDIUM_ORANGE
    FG_PRELIGHT_COLOR = 'black'
    FG_ACTIVE_COLOR = 'white'

    NUMBER_FG_COLORS = {'normal': MEDIUM_ORANGE, 'prelight': 'white', 'active': 'white'}
    IN_OUT_FG_COLORS = {'normal': BRIGHT_ORANGE, 'prelight': LIGHT_GREY2, 'active': DARK_GREY}
    SIGNAL_FG_COLORS = {'normal': LIGHT_GREY1, 'prelight': LIGHT_GREY2, 'active': DARK_GREY}
    EXTRA_FG_COLORS = {'normal': LIGHT_YELLOW, 'prelight': LIGHT_GREY2, 'active': DARK_GREY}

    # see https://developer.gnome.org/pygtk/stable/pango-markup-language.html
    NUMBER_MARKUP = '<span font_family="monospace" weight="ultrabold" size="x-large">{}</span>'
    IN_OUT_MARKUP = '<span font_family="monospace" size="small">{}</span>'
    SIGNAL_MARKUP = '<span font_family="sans" size="medium">{}</span>'
    EXTRA_MARKUP = '<span font_family="sans" size="small">{}</span>'

    def __init__(self, pin_number, in_out_text, signal_text, extra_text=None, activate_on_click=True, border_width=5):
        # TODO add arguments for per-field-colors
        self.activate_on_click = activate_on_click

        if isinstance(pin_number, int) and pin_number < 100:
            # always have number be 2 positions
            pin_number = '{:02d}'.format(pin_number)
        else:
            pin_number = str(pin_number)

        labels_box = gtk.VBox(homogeneous=False, spacing=2)
        super(InputButton, self).__init__(widget=labels_box)

        top_labels = gtk.HBox(homogeneous=False, spacing=0)
        bot_labels = gtk.HBox(homogeneous=False, spacing=0)

        num_label = gtk.Label()
        num_label.set_alignment(0.0, 0.0)
        num_label.set_justify(gtk.JUSTIFY_LEFT)
        num_label.set_size_request(-1, 20)
        self.set_child_colors(num_label, 'fg', **self.NUMBER_FG_COLORS)

        in_out_label = gtk.Label()
        in_out_label.set_alignment(1, 0.0)
        in_out_label.set_justify(gtk.JUSTIFY_RIGHT)
        in_out_label.set_size_request(100, 10)
        self.set_child_colors(in_out_label, 'fg', **self.IN_OUT_FG_COLORS)

        signal_label = gtk.Label()
        signal_label.set_alignment(0.0, 0.5)
        self.set_child_colors(signal_label, 'fg', **self.SIGNAL_FG_COLORS)

        extra_label = gtk.Label()
        extra_label.set_alignment(1, 0.5)
        extra_label.set_justify(gtk.JUSTIFY_RIGHT)
        self.set_child_colors(extra_label, 'fg', **self.EXTRA_FG_COLORS)

        labels = ((num_label, self.NUMBER_MARKUP.format(pin_number)),
                  (in_out_label, self.IN_OUT_MARKUP.format(in_out_text)),
                  (signal_label, self.SIGNAL_MARKUP.format(signal_text)),
                  (extra_label, self.EXTRA_MARKUP.format(extra_text)))

        for label, markup in labels:
            label.set_use_markup(True)
            label.set_markup(markup)
            label.set_property('single-line-mode', True)
            label.set_padding(5, 2)

        top_labels.pack_start(num_label, expand=False, fill=False, padding=0)
        top_labels.pack_end(in_out_label, expand=True, fill=True, padding=0)

        bot_labels.pack_start(signal_label, expand=True, fill=True, padding=0)
        if extra_text is not None:
            bot_labels.pack_end(extra_label, expand=False, fill=False, padding=0)

        labels_box.pack_start(top_labels, expand=False, fill=False, padding=0)
        labels_box.pack_start(bot_labels, expand=False, fill=False, padding=0)

        self.set_button_state(False)
        self.set_size_request(*self.DEFAULT_SIZE)
        self.set_border_width(border_width)

    def on_press(self, widget, event):
        if self.activate_on_click:
            self.set_button_state(not self.active)


class OutputButton(InputButton):
    DEFAULT_SIZE = (250, 50)
    VERY_LIGHT_BLUE = '#bde0ff'
    PALE_BLUE = '#75bfff'
    LIGHT_BLUE1 = '#348cf7'
    MEDIUM_BLUE = '#0a6cff'
    MEDIUM_BLUE2 = '#1c77b8'
    MEDIUM_BLUE3 = '#2796e6'
    BRIGHT_BLUE = '#005eff'
    LIGHT_GREY1 = '#b8b8b8'
    LIGHT_GREY2 = '#b5b5b5'
    MED_GREY = '#525252'
    DARK_GREY = '#292929'
    DARK_GREY2 = '#212121'

    BG_NORMAL_COLOR = 'black'
    BG_PRELIGHT_COLOR = DARK_GREY2
    BG_ACTIVE_COLOR = MEDIUM_BLUE2

    FG_NORMAL_COLOR = MEDIUM_BLUE3
    FG_PRELIGHT_COLOR = 'black'
    FG_ACTIVE_COLOR = 'white'

    NUMBER_FG_COLORS = {'normal': MEDIUM_BLUE3, 'prelight': 'white', 'active': 'white'}
    IN_OUT_FG_COLORS = {'normal': PALE_BLUE, 'prelight': LIGHT_GREY2, 'active': VERY_LIGHT_BLUE}
    SIGNAL_FG_COLORS = {'normal': LIGHT_GREY1, 'prelight': LIGHT_GREY2, 'active': VERY_LIGHT_BLUE}
    EXTRA_FG_COLORS = {'normal': LIGHT_BLUE1, 'prelight': LIGHT_GREY2, 'active': DARK_GREY}

    # see https://developer.gnome.org/pygtk/stable/pango-markup-language.html
    NUMBER_MARKUP = '<span font_family="monospace" weight="ultrabold" size="x-large">{}</span>'
    IN_OUT_MARKUP = '<span font_family="monospace" weight="bold" size="small">{}</span>'
    SIGNAL_MARKUP = '<span font_family="sans" size="medium">{}</span>'
    EXTRA_MARKUP = '<span font_family="sans" size="small">{}</span>'


class IOButtonsBox(gtk.HBox):

    def __init__(self, rows_per_column):
        super(IOButtonsBox, self).__init__(homogeneous=False, spacing=0)
        self._rows_vboxs = []
        self._btn_index = {}
        self._rows_per_column = rows_per_column
        self.add_column()

    def add_column(self):
        """
        adds an additional column and packs it into the button box

        The container for the column is returned
        :return:
        """
        column = gtk.VBox()
        self._rows_vboxs.append(column)
        # no padding between vboxs, the widgets themselves provide padding and a border
        self.pack_start(column, expand=False, fill=False, padding=0)
        return column

    def column_count(self):
        return len(self._rows_vboxs)

    def current_column_has_room(self):
        last_column = self._rows_vboxs[-1]
        num_rows = len(last_column.get_children())
        return num_rows < self._rows_per_column

    def add_button(self, name, button_obj):
        if not self.current_column_has_room():
            self.add_column()

        # the button is packed into an HBox, this prevents it from expanding horizontally and filling all
        # available width.
        btn_hbox = gtk.HBox()
        btn_hbox.pack_start(button_obj, False, False, padding=0)
        column_vbox = self._rows_vboxs[-1]
        column_vbox.pack_start(btn_hbox, expand=False, fill=False, padding=0)
        button_obj.set_name(name)
        self._btn_index[name] = button_obj

    def get_button_size_request(self):
        if self._btn_index.has_key(0):
            return self._btn_index[0].get_size_request()

    def get_column_size_request(self):
        return self.rows_vboxs[0].get_size_request()

    def get_button(self, btn_name):
        return self._btn_index.get(btn_name)

    def set_button_state(self, btn_name, active):
        btn = self._btn_index.get(btn_name)
        if not btn:
            raise NameError('no button named: {}'.format(btn_name))
        btn.set_button_state(active)

    def items(self):
        """
        Returns iterator of tuples (name, ButtonObj)
        :return:
        """
        return self._btn_index.items()

    def __iter__(self):
        for btn in self.btn_index.values():
            yield btn

    def __len__(self):
        return len(self._btn_index)


class IOPanel(gtk.ScrolledWindow):
    COMPONENT_NAME = 'iopanel'
    BUTTONS_PER_ROW = 10
    UPDATE_FREQUENCY_MILLIS = 1000

    def __init__(self,
                 component_name,
                 hal_component,
                 hal_in_label='output',
                 hal_out_label='input',
                 hal_in_button=OutputButton,
                 hal_out_button=InputButton,
                 first_pin=0,
                 columns=4):
        # member variables
        super(IOPanel, self).__init__()
        self._update_loop = False  # is the update loop running?
        self._btn_boxes = {}
        self._pins = []
        self._hal_component = hal_component
        self._component_name = component_name
        self._hal_in_label = hal_in_label
        self._hal_out_label = hal_out_label
        self._hal_in_button = hal_in_button
        self._hal_out_button = hal_out_button
        self._first_pin = first_pin
        self._column_count = columns

        self._container = gtk.VBox()
        self.add_with_viewport(self._container)
        self.set_border_width(0)
        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_NONE)
        self.get_child().modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#292929'))

    @property
    def component_name(self):
        return self._component_name

    def add_button_box(self, name, rows_per_column):
        """
        Adds a button box to the current widget

        :param name: The name of the button box, for our own reference
        :param rows_per_column: controls how many rows are drawn per column in the Button box
        :return: The newly created Button Box
        :rtype: IOButtonsBox

        """
        box = IOButtonsBox(rows_per_column=rows_per_column)
        box.set_name(name)
        self._btn_boxes[name] = box
        self._container.pack_start(box, expand=False, fill=False, padding=0)
        return box

    def get_button_box(self, name):
        """
        Return the button container widget by name
        Through the button box you can access its buttons by name

        :param name:
        :return: Button Box instance
        :rtype: IOButtonsBox
        """
        return self._btn_boxes.get(name)

    def get_component_pins(self, direction=None):
        """
        Retrieve component pin information

        The returned data structure is a sequence of dictionaries sorted by pin-name

        Each dictionary will contain the contents:
        {
            'pin': <pin-name>,
            'signal': <signal-name>,
            'direction': <direction-constant',
        }

        The data returned is sourced from these two HAL api calls

        >>> pprint( hal.get_info_pins() )
        [
            {'NAME': 'mega2560.input-00', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            {'NAME': 'mega2560.input-01', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            {'NAME': 'mega2560.input-02', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            {'NAME': 'mega2560.input-03', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            ...
            {'NAME': 'mega2560.output-00', 'VALUE': False, 'DIRECTION': hal.HAL_IN},
        ]


        >>> pprint( hal.get_info_signals() )
        [
            {'NAME': 'input-controller-on', 'VALUE': False, 'DRIVER': 'mega2560.input-00'},
            {'NAME': 'input-fault-pump-overload', 'VALUE': False, 'DRIVER': 'mega2560.input-01'},
            {'NAME': 'input-door-disconnect', 'VALUE': False, 'DRIVER': 'mega2560.input-02'},
        ]

        :param direction: one of the constants (hal.HAL_OUT, hal.HAL_IN)
        :return:
        """
        try:
            all_pins = hal.get_info_pins()
            all_signals = hal.get_info_signals()
        except AttributeError:
            all_pins = HalCmd.get_info_pins()
            all_signals = HalCmd.get_info_signals()

        log.debug('get_component_pins - hal returned {} pins, {} signals'.format(len(all_pins), len(all_signals)))

        # filter signals for our component, if component isn't set, collect all signals
        pin_signals = {}
        for signal in all_signals:
            signal_name = signal.get('NAME')
            pin_name = signal.get('DRIVER', '')
            if self.component_name is None or str(pin_name).startswith(self.component_name):
                pin_signals[pin_name] = signal_name
            for reader in signal.get('READERS', []):
                if self.component_name is None or str(reader).startswith(self.component_name):
                    pin_signals[reader] = signal_name

        log.debug(pformat(pin_signals))

        # filter signals for our component, if component isn't set, collect all signals
        pins = []
        for pin in all_pins:
            # exclude NOT (inverse) pins
            if pin.get('NAME', '').lower().endswith('not'):
                continue
            if self.component_name and not pin.get('NAME', '').startswith(self.component_name):
                continue
            if direction is not None and pin.get('DIRECTION', None) != direction:
                continue
            pins.append({'pin': pin['NAME'], 'signal': pin_signals.get(pin['NAME']), 'direction': pin['DIRECTION']})

        log.debug(pformat(pins))

        log.debug('get_component_pins - matched {} pins, {} signals to component: {}'.format(
            len(pins), len(pin_signals), self.component_name))

        return sorted(pins, key=lambda i: i['pin'])

    def get_pin_values(self, direction=None):
        """
        Return dictionary of {"pin-name": <pin-value>}

        :return:
        """
        try:
            all_pins = hal.get_info_pins()
        except AttributeError:
            all_pins = HalCmd.get_info_pins()

        pin_vals = {}
        pin_count = 0
        for pin in all_pins:
            pin_count += 1
            # exclude NOT (inverse) pins
            if pin.get('NAME', '').lower().endswith('not'):
                continue
            if self.component_name and not pin.get('NAME', '').startswith(self.component_name or ''):
                continue
            if direction is not None and pin.get('DIRECTION', None) != direction:
                continue
            pin_vals[pin['NAME']] = pin['VALUE']
        return pin_vals

    def on_realize(self, window):
        """
        Called when the main window is made ready/drawn via "realize"

        :param window: main window object
        :return:
        """
        log.debug('{} on realize signal received'.format(self.__class__.__name__))
        self.populate()
        if not self._update_loop:
            self.start_updates()

    def start_updates(self):
        gobject.timeout_add(self.UPDATE_FREQUENCY_MILLIS, self.update)
        self._update_loop = True

    def populate(self):
        """
        Build ui based on pins available for this component name
        """
        log.info('populating interface')

        ins = self.get_component_pins(direction=hal.HAL_IN)
        ins_rows_count = len(ins)
        # NOTE: gtk3 can dynamically layout the buttons based on a Flow container... for when that day comes
        ins_rows_per_column = math.ceil(float(ins_rows_count) / float(self._column_count))
        in_box = self.add_button_box(name=self._hal_in_label, rows_per_column=ins_rows_per_column)

        outs = self.get_component_pins(direction=hal.HAL_OUT)
        outs_rows_count = len(outs)
        outs_rows_per_column = math.ceil(float(outs_rows_count) / float(self._column_count))
        out_box = self.add_button_box(name=self._hal_out_label, rows_per_column=outs_rows_per_column)

        # setup the buttons for all "hal.HAL_IN" pins
        for pin_idx, hal_in in enumerate(ins, start=self._first_pin):
            pin_name = self.format_pin_number(hal_in['pin'])
            InCls = self._hal_in_button
            # TODO implement categories for extra_text
            # TODO allow optimizing style from metadata here
            in_btn = InCls(pin_number=pin_name,
                           in_out_text=self._hal_in_label,
                           signal_text=hal_in['signal'] or hal_in['pin'],
                           extra_text=None,
                           activate_on_click=False)
            in_box.add_button(name=hal_in['pin'], button_obj=in_btn)
            log.debug('adding button {}: {} - {}'.format(self._hal_in_label, hal_in['pin'], hal_in['signal']))

        # setup the buttons for all "hal.HAL_OUT" pins
        for pin_idx, hal_out in enumerate(outs, start=self._first_pin):
            pin_name = self.format_pin_number(hal_out['pin'])
            OutCls = self._hal_out_button
            # TODO implement categories for extra_text
            # TODO allow optimizing style from metadata here
            out_btn = OutCls(pin_number=pin_name,
                             in_out_text=self._hal_out_label,
                             signal_text=hal_out['signal'] or hal_out['pin'],
                             extra_text=None,
                             activate_on_click=False)
            out_box.add_button(name=hal_out['pin'], button_obj=out_btn)
            log.debug('adding button {}: {} - {}'.format(self._hal_out_label, hal_out['pin'], hal_out['signal']))

        self.show_all()
        if not self._update_loop:
            self.start_updates()

    def update(self):
        """
        Apply hal pin status to buttons, updating their visual representation based on pin value
        """
        log.debug('updating pin states')
        for io_label, hal_direction in {self._hal_in_label: hal.HAL_IN, self._hal_out_label: hal.HAL_OUT}.items():
            button_box = self.get_button_box(io_label)
            if not button_box:
                continue
            for pin_name, state in self.get_pin_values(direction=hal_direction).items():
                log.debug('{} => {}'.format(pin_name, state))
                button_box.set_button_state(btn_name=pin_name, active=state)

        return True

    def format_pin_number(self, pin_name):
        """
        Format the pin name

        :param pin_name:
        :type pin_name: str
        :return:
        """
        parts = pin_name.split('.', 1)
        minus_comp = parts[-1]
        parts = []
        for char in '-._':
            if char in minus_comp:
                parts = minus_comp.split(char)
        number = minus_comp
        for find_number in parts:
            find_number = re.sub('[^0-9]', '', find_number)
            if find_number.isdigit():
                number = find_number

        return number


def main():
    window = gtk.Window()
    window.set_title("IO Status")
    window.set_position(gtk.WIN_POS_CENTER)
    window.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#292929'))
    '''
        window_width = min(self.MAX_INITIAL_WIDTH, inputs_box.get_size_request()[0])
        window_height = min(self.MAX_INITIAL_HEIGHT, inputs_box.get_size_request()[1])
        window.set_size_request(window_width, window_height)
        window.add(pane)
        window.connect("destroy", gtk.main_quit)
        window.show_all()

    '''
    panel = IOPanel(window)
    window.add(panel)


if __name__ == '__main__':
    sys.exit(main())


class HalInfoCommon(object):

    def __init__(self, hal_type, value):
        self._hal_type = None
        self._value = None

        self.hal_type = hal_type  # important this is done first
        self.value = value

    @property
    def hal_type(self):
        return self._hal_type

    @hal_type.setter
    def hal_type(self, hal_type):
        if isinstance(hal_type, str):
            hal_type = getattr(hal, 'HAL_{}'.format(hal_type.upper()))
        self._hal_type = hal_type

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        # if hal_type is set before us, use the type to format the value
        if self.hal_type == hal.HAL_BIT:
            orig_value = value
            value = True if value.lower() == str(True).lower() else False
        elif self.hal_type in (hal.HAL_S32, hal.HAL_U32):
            value = int(value, 0)  # parse hexadecimal (int("0xdeadbeef", 0))
        elif self.hal_type == hal.HAL_FLOAT:
            value = float(value)
        elif isinstance(value, str):
            if value.lower() == str(False).lower():
                value = False
            elif value.lower() == str(True).lower():
                value = True
            else:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    try:
                        value = float(value)
                    except ValueError:
                        pass

        self._value = value


class HalSignalInfo(HalInfoCommon):
    DRIVER_TYPE = '<=='
    READER_TYPE = '==>'
    BIDIRECTIONAL_TYPE = '<==>'
    DIRECTIONS = set((DRIVER_TYPE, READER_TYPE, BIDIRECTIONAL_TYPE))

    def __init__(self, hal_type, name, value, driver, readers, bidirectional):
        super(HalSignalInfo, self).__init__(hal_type, value)
        self._name = None
        self._driver = None
        self._readers = None
        self._bidirectional = None

        self.name = name
        self.driver = driver
        self.readers = readers
        self.bidirectional = bidirectional

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        if not isinstance(name, str):
            raise ValueError('name must be str, not {}'.format(type(name)))
        self._name = name


    @property
    def driver(self):
        return self._driver

    @driver.setter
    def driver(self, driver):
        if driver is not None and not isinstance(driver, str):
            raise ValueError('driver must be str, not {}'.format(type(driver)))
        self._driver = driver

    @property
    def readers(self):
        return self._readers

    @readers.setter
    def readers(self, readers):
        if not isinstance(readers, (list, tuple)):
            raise ValueError('readers must be list/tuple, not {}'.format(type(readers)))
        self._readers = readers

    @property
    def bidirectional(self):
        return self._bidirectional

    @bidirectional.setter
    def bidirectional(self, bidirectional):
        if not isinstance(bidirectional, (list, tuple)):
            raise ValueError('bidirectional must be list/tuple, not {}'.format(type(bidirectional)))
        self._bidirectional = bidirectional

    @classmethod
    def from_str(cls, signals):
        lines = signals.splitlines()
        return cls.from_parts(lines)

    @classmethod
    def from_parts(cls, signal):
        """
        Parses lines of input:

            bit           FALSE  input-carousel-change-position-impulse
                                     <== mega2560.input-22
        :param signal: a sequence of text lines, forming a single signal description
        :return:
        """
        if len(signal) < 2:
            return None

        signal_attrs = signal[0]
        signal_attrs = signal_attrs.strip().split()
        if len(signal_attrs) != 3:
            return None
        hal_type, raw_value, signal_name = signal_attrs

        signal_pins = signal[1:]
        driver = None
        readers = []
        bidirectional = []
        for signal_line in signal_pins:
            signal_pin = signal_line.strip().split()
            if len(signal_pin) != 2:
                continue
            signal_type, pin_name = signal_pin
            if signal_type == cls.DRIVER_TYPE:
                driver = pin_name
            elif signal_type == cls.READER_TYPE:
                readers.append(pin_name)
            elif signal_type == cls.BIDIRECTIONAL_TYPE:
                bidirectional.append(pin_name)

        return cls(hal_type=hal_type, name=signal_name, value=raw_value, driver=driver, readers=readers, bidirectional=bidirectional)


class HalPinInfo(HalInfoCommon):
    BIDIRECTIONAL = 'I/O'
    IGNORE = ['Component Pins:', 'Owner   Type  Dir         Value  Name']
    PROPERTIES = ['hal_type', 'direction', 'value', 'name', 'signal']

    def __init__(self, hal_type, direction, value, name, signal=None):
        super(HalPinInfo, self).__init__(hal_type, value)
        self._direction = None
        self._name = None
        self._signal = None

        self.direction = direction
        self.name = name
        self.signal = signal

    @property
    def component(self):
        """
        Return the name of the component
        """
        if self.name is not None:
            return self.name.split('.', 1)[0]

    @property
    def direction(self):
        return self._direction

    @direction.setter
    def direction(self, direction):
        if isinstance(direction, str):
            if direction == self.BIDIRECTIONAL:
                self._direction = None
            else:
                direction = getattr(hal, 'HAL_{}'.format(direction.upper()))
        self._direction = direction

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @classmethod
    def from_str(cls, hal_output):
        log.debug('parsing hal_output %s', hal_output)
        if hal_output.strip() in cls.IGNORE:
            log.debug('ignoring %s', hal_output)
            return None

        parts = hal_output.strip().split()
        return cls.from_parts(parts)

    @classmethod
    def from_parts(cls, hal_parts):
        """

        :param hal_parts: a sequence of 5 or 7 positions
        :type hal_parts: list
        :return:
        """
        if len(hal_parts) == 5:
            hal_parts.extend([None, None])

        if len(hal_parts) == 7:
            # we don't need the 5th and 0th index item
            del hal_parts[5]  # remove direction arrows
            del hal_parts[0]  # remove 'owner'
            kwargs = dict(zip(cls.PROPERTIES, hal_parts))
            return cls(**kwargs)
        else:
            log.debug('hal parts didnnt match %s', hal_parts)
            return None


class HalCmd:
    TYPES = set(['bit', 'float', 's32', 'u32'])
    HAL_PIN_CMD = 'halcmd show pin'
    HAL_SIG_CMD = 'halcmd show sig'
    HAL_COMP_CMD = 'halcmd show comp'

    @classmethod
    def exec_halcmd_show_comp(cls):
        """
        Returns sequence of HalCompInfo()

        Parses hal output

                    Loaded HAL Components:
            ID      Type  Name                                            PID   State
                69  User  halcmd26530                                     26530 ready
                53  User  axisui                                          24597 ready
                51  User  inihal                                          24594 ready
                44  User  mega2560                                        24577 ready
                40  RT    toggle2nist                                           ready
                37  RT    toggle                                                ready
                34  RT    estop_latch                                           ready
                31  RT    pid                                                   ready
                28  RT    hm2_pci                                               ready
                25  RT    hostmot2                                              ready
                22  RT    __servo-thread                                        ready
                21  RT    motmod                                                ready
                18  RT    trivkins                                              ready
                12  User  halui                                           24562 ready
                 6  User  iocontrol                                       24560 ready

        :return:
        """

    @classmethod
    def exec_halcmd_show_pin(cls):
        """
        Return sequence of HalPinInfo()

        Parses hal output:

            Component Pins:
            Owner   Type  Dir         Value  Name
                21  bit   OUT          TRUE  axis.0.active
                21  bit   OUT         FALSE  axis.0.amp-enable-out ==> x-enable
                21  bit   IN          FALSE  axis.0.amp-fault-in
                21  float OUT             0  axis.0.backlash-corr
                21  float OUT             0  axis.0.backlash-filt
                21  float OUT             0  axis.0.backlash-vel
                21  float OUT             0  axis.0.coarse-pos-cmd
                21  bit   OUT         FALSE  axis.0.error
                21  float OUT             0  axis.0.f-error
                21  float OUT             1  axis.0.f-error-lim
                21  bit   OUT         FALSE  axis.0.f-errored
                21  bit   OUT         FALSE  axis.0.faulted
                21  float OUT             0  axis.0.free-pos-cmd
                21  bit   OUT         FALSE  axis.0.free-tp-enable
                21  float OUT             0  axis.0.free-vel-lim
                21  s32   OUT             0  axis.0.home-state
                21  bit   IN          FALSE  axis.0.home-sw-in <== input-x-axis-limit
        :return:
        """
        pins = subprocess.check_output(cls.HAL_PIN_CMD, shell=True)
        log.debug('hal cmd pin output: {}'.format(pins))
        for pin_line in pins.strip().splitlines():
            # parse the pin-line into a data structure, if the line cannot be parsed None is returned
            pin_info = HalPinInfo.from_str(pin_line)
            if pin_info:
                #print('in line:', pin_line)
                #print('pin value:', pin_info.value)
                log.debug('hal found pin: {}'.format(pin_info.name))
                yield pin_info

    @classmethod
    def exec_halcmd_show_sig(cls):
        """
        Return sequence of HalSignalInfo()

        Parses:

            Signals:
            Type          Value  Name     (linked to)
            bit           FALSE  estop-loopin
                                     ==> estop-latch.0.ok-in
                                     <== iocontrol.0.user-enable-out
            bit           FALSE  estop-loopout
                                     <== estop-latch.0.ok-out
                                     ==> iocontrol.0.emc-enable-in
            bit           FALSE  estop-reset
                                     ==> estop-latch.0.reset
                                     <== iocontrol.0.user-request-enable
            bit           FALSE  input-carousel-change-position-impulse
                                     <== mega2560.input-22
            bit           FALSE  input-carousel-check-up-tool
                                     <== mega2560.input-25
            bit           FALSE  input-carousel-position-headstock
        """
        signals = subprocess.check_output(cls.HAL_SIG_CMD, shell=True)
        signal_groups = []
        current_group = []
        for signal_line in signals.strip().splitlines():
            signal_line = signal_line.strip()
            signal_parts = signal_line.split()
            if not signal_parts:
                continue
            if signal_parts[0] in cls.TYPES:
                if current_group:
                    signal_groups.append(current_group)
                    current_group = []
                current_group.append(signal_line)
            elif signal_parts[0] in HalSignalInfo.DIRECTIONS:
                current_group.append(signal_line)

        if current_group:
            signal_groups.append(current_group)

        for signal in signal_groups:
            sig_info = HalSignalInfo.from_parts(signal)
            if sig_info:
                yield sig_info

    @classmethod
    def get_info_pins(cls):
        """
        Simulates the response of the `hal.get_info_pins()` function
        by querying the halcmd cli directly

        >>> pprint( hal.get_info_pins() )
        [
            {'NAME': 'mega2560.input-00', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            {'NAME': 'mega2560.input-01', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            {'NAME': 'mega2560.input-02', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            {'NAME': 'mega2560.input-03', 'VALUE': False, 'DIRECTION': hal.HAL_OUT},
            ...
            {'NAME': 'mega2560.output-00', 'VALUE': False, 'DIRECTION': hal.HAL_IN},
        ]

        :return:
        """
        return [{'NAME': pin.name, 'VALUE': pin.value, 'DIRECTION': pin.direction} for pin in cls.exec_halcmd_show_pin()]

    @classmethod
    def get_info_signals(cls):
        """
        Simulates the response of the `hal.get_info_signals()` function
        by querying the halcmd cli directly

        >>> pprint( hal.get_info_signals() )
        [
            {'NAME': 'input-controller-on', 'VALUE': False, 'DRIVER': 'mega2560.input-00'},
            {'NAME': 'input-fault-pump-overload', 'VALUE': False, 'DRIVER': 'mega2560.input-01'},
            {'NAME': 'input-door-disconnect', 'VALUE': False, 'DRIVER': 'mega2560.input-02'},
        ]

        :return:
        """
        return [{'NAME': sig.name, 'VALUE': sig.value, 'DRIVER': sig.driver, 'READERS': sig.readers} for sig in cls.exec_halcmd_show_sig()]


class HandlerClass:
    """
    Interacts with linuxcnc `gladvcp` plugin.

    GladeVCP looks for the function "get_handlers" in this python module and calls it.
    This gives us a hook into creating our interface
    """
    COMPONENT_ARGUMENT = 'component'

    def __init__(self, halcomp, builder, useropts):
        """
        Handler classes are instantiated in the following state:
        - the widget tree is created, but not yet realized (no toplevel window.show() executed yet)
        - the halcomp HAL component is set up and the widhget tree's HAL pins have already been added to it
        - it is safe to add more hal pins because halcomp.ready() has not yet been called at this point.
        after all handlers are instantiated in command line and get_handlers() order, callbacks will be
        connected with connect_signals()/signal_autoconnect()
        The builder may be either of libglade or GtkBuilder type depending on the glade file format.

        :param useropts: any user options passed into halcmd: gladevcp -U debug=42 -U "print 'debug=%d' % debug" ...
        :type useropts: list
        """
        log.info('useropts: {}'.format(useropts))

        self.halcomp = halcomp
        self.builder = builder
        self.nhits = 0
        self.panel = None

        window = builder.get_object("window1")  # get the window
        if window is None:
            all_objs = builder.get_objects()
            names = []
            for obj in all_objs:
                try:
                    names.append(obj.get_name())
                except Exception as e:
                    pass
            raise ValueError('cannot find "window1" - {}'.format(names))

        component_name = None
        for argument in useropts:
            if argument.startswith(self.COMPONENT_ARGUMENT) and '=' in argument:
                component_name = argument.split('=', 1)[-1]

        self.main(window, component_name)

    def main(self, window, component_name):
        self.panel = IOPanel(component_name=component_name, hal_component=self.halcomp)
        self.panel.populate()
        window.connect("show", self.panel.on_realize)
        window.connect("realize", self.panel.on_realize)
        window.add(self.panel)

    def on_realize(self, window):
        """
        Called when LinuxCNC makes the main window "ready"
        :return:
        """


def get_handlers(halcomp, builder, useropts):
    return [HandlerClass(halcomp, builder, useropts)]
