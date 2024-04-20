from __future__ import print_function

import sys
from itertools import islice
import gtk

INPUT_NAMES = '''
CNC CONTROL ON/OFF
Coolant Pump Overloaded
Door Disconnected
Feed Drives Power Master Power
Front Door Closed (Open Contact)
Front Door Open (Closed Contact)
Spindle - Zero Speed (Stopped)
Spindle - Speed Agreed
Spindle - Torque Detection
Spindle - Fault
Feed Alarm
Servo Drives Overloaded (XYZ)
Tool Changer - Air Pressure Attained
Tool Changer - Tool Releasing
Tool Changer - Check Tool Clamped Proximity Switch
Tool Changer - Tool Unclamped Proximity Switch
Tool Changer - Tool Clamped Proximity Switch
Tool Changer - Carousel Check UP Position
X Axis Reference Trip Dog (limit switch)
Y Axis Reference Trip Dog
Z Axis Reference Trip Dog
Tool Changer - Carousel Reference Point (0 position)
Tool Changer - Carousel Impulse on Change of Position 2 WIRE
Tool Changer - Carousel Position Left
Tool Changer - Carousel Position Right (By HeadStock)
Tool Changer - Carousel Check Up Tool
Tool Changer - Carousel Motor Overloaded
'''.strip().splitlines()

OUTPUT_NAMES = '''
NC READY ESTPO
Tool Changer - Tool in spindle clamp/unclamp
Spindle Airblast
Spindle Forward Run
Spindle Alarm Reset
Spindle Speed Regulator - P/PI Selection
Servo Drives On (XYZ)
Coolant Pump Internal (Through HeadStock)
24V Return (galvanized)
Tool Changer - Carousel Clockwise - Unbrake
Tool Changer - Carousel Counter-Clockwise
Tool Changer - Carousel Left M1
Tool Changer - Carousel Right M1
Alarm Reset
'''.strip().splitlines()

ALARMS = [
    'Feed Alarm',
    'Spindle - Fault',
    'Servo Drives Overloaded (XYZ)',
    'Tool Changer - Carousel Motor Overloaded',
    'Coolant Pump Overloaded'
]


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

    def on_enter(self, widget, event):
        widget.get_window().set_cursor(gtk.gdk.Cursor(self.CURSOR_PRELIGHT))
        self.activate_prelight_style()

    def on_leave(self, widget, event):
        widget.get_window().set_cursor(None)
        self.set_button_state()

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
    NUMBER_MARKUP = '<span font_family="monospace" weight="ultrabold" size="xx-large">{}</span>'
    IN_OUT_MARKUP = '<span font_family="monospace" size="small">{}</span>'
    SIGNAL_MARKUP = '<span font_family="sans" size="medium">{}</span>'
    EXTRA_MARKUP = '<span font_family="sans" size="small">{}</span>'

    def __init__(self, pin_number, in_out_text, signal_text, extra_text=None, activate_on_click=True, border_width=5):
        # TODO add arguments for per-field-colors
        self.activate_on_click = activate_on_click

        if isinstance(pin_number, int):
            # always have number be 2 positions
            pin_number = '{:02d}'.format(pin_number)

        labels_box = gtk.VBox(homogeneous=False, spacing=2)
        super(InputButton, self).__init__(widget=labels_box)

        top_labels = gtk.HBox(homogeneous=False, spacing=0)
        bot_labels = gtk.HBox(homogeneous=False, spacing=0)

        num_label = gtk.Label()
        num_label.set_alignment(0.0, 0.0)
        num_label.set_justify(gtk.JUSTIFY_LEFT)
        num_label.set_size_request(30, 20)
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
    NUMBER_MARKUP = '<span font_family="monospace" weight="ultrabold" size="xx-large">{}</span>'
    IN_OUT_MARKUP = '<span font_family="monospace" weight="bold" size="small">{}</span>'
    SIGNAL_MARKUP = '<span font_family="sans" size="medium">{}</span>'
    EXTRA_MARKUP = '<span font_family="sans" size="small">{}</span>'


class IOButtonsBox(gtk.HBox):

    def __init__(self, btn_class, row_data, column_count):
        super(IOButtonsBox, self).__init__(homogeneous=False, spacing=0)

        self.column_count = column_count
        num_rows = len(row_data)

        self.rows_vboxs = []
        self.btn_index = {}

        for sequence in chunk(range(num_rows), int(num_rows / self.column_count)):
            rows_vbox = gtk.VBox()
            self.rows_vboxs.append(rows_vbox)
            for idx in sequence:
                btn_fields = row_data[idx]
                btn_hbox = gtk.HBox()
                # pin_number, in_out_text, signal_text, extra_text
                btn = btn_class(**btn_fields)
                self.btn_size = btn.get_size_request()
                btn_hbox.pack_start(btn, False, False, padding=0)
                rows_vbox.pack_start(btn_hbox, expand=False, fill=False, padding=0)
                self.btn_index[idx] = btn

            self.pack_start(rows_vbox, expand=False, fill=False, padding=0)

    def get_button_size_request(self):
        if self.btn_index.has_key(0):
            return self.btn_index[0].get_size_request()

    def get_column_size_request(self):
        return self.rows_vboxs[0].get_size_request()

    def get_button(self, btn_idx):
        return self.btn_index.get(btn_idx)

    def set_button_state(self, btn_idx, active):
        self.btn_index.get(btn_idx).set_button_state(active)

    def __iter__(self):
        for btn in self.btn_index.values():
            yield btn


class PyApp:
    NUM_COLUMNS = 3
    MAX_INITIAL_WIDTH = 640
    MAX_INITIAL_HEIGHT = 480

    def __init__(self, window):
        window.set_title("IO Status")
        window.set_position(gtk.WIN_POS_CENTER)
        window.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#292929'))

        # construct a list of dictionaries with the keys: pin_number, in_out_text, signal_text, extra_text
        input_data = [{'pin_number': idx, 'in_out_text': 'input', 'signal_text': name, 'activate_on_click': False} for idx, name in enumerate(INPUT_NAMES)]
        inputs_box = IOButtonsBox(btn_class=InputButton, row_data=input_data, column_count=3)
        scroll_top = self.create_scroll_window(inputs_box)

        output_data = [{'pin_number': idx, 'in_out_text': 'output', 'signal_text': name, 'activate_on_click': True} for idx, name in enumerate(OUTPUT_NAMES)]
        outputs_box = IOButtonsBox(btn_class=OutputButton, row_data=output_data, column_count=3)
        scroll_bottom = self.create_scroll_window(outputs_box)

        pane = gtk.VPaned()
        pane.add1(scroll_top)
        pane.add2(scroll_bottom)

        window_width = min(window.MAX_INITIAL_WIDTH, inputs_box.get_size_request()[0])
        window_height = min(window.MAX_INITIAL_HEIGHT, inputs_box.get_size_request()[1])
        window.set_size_request(window_width, window_height)
        window.add(pane)
        window.connect("destroy", gtk.main_quit)
        window.show_all()

    def create_scroll_window(self, widget):
        scroll = gtk.ScrolledWindow()
        scroll.add_with_viewport(widget)
        scroll.set_border_width(0)
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.set_shadow_type(gtk.SHADOW_NONE)
        scroll.get_child().modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#292929'))
        return scroll


def main():
    builder = gtk.Builder()
    #builder.add_from_file("iopanel.glade")
    window = builder.get_object("window1")
    app = PyApp(window)
    import hal
    io = hal.component('iopanel')
    io.ready()


if __name__ == '__main__':
    sys.exit(main())


class HandlerClass:
    '''
    class with gladevcp callback handlers
    '''

    def __init__(self, halcomp, builder, useropts):
        '''
        Handler classes are instantiated in the following state:
        - the widget tree is created, but not yet realized (no toplevel window.show() executed yet)
        - the halcomp HAL component is set up and the widhget tree's HAL pins have already been added to it
        - it is safe to add more hal pins because halcomp.ready() has not yet been called at this point.
        after all handlers are instantiated in command line and get_handlers() order, callbacks will be
        connected with connect_signals()/signal_autoconnect()
        The builder may be either of libglade or GtkBuilder type depending on the glade file format.
        '''

        self.halcomp = halcomp
        self.builder = builder
        self.nhits = 0

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
        PyApp()

    """
    def on_button_press(self,widget,data=None):
        '''
        a callback method
        parameters are:
            the generating object instance, likte a GtkButton instance
            user data passed if any - this is currently unused but
            the convention should be retained just in case
        '''
        print("on_button_press called")
        self.nhits += 1
        self.builder.get_object('hits').set_label("Hits: %d" % (self.nhits)) 
    """

from gladevcp.persistence import IniFile,widget_defaults,set_debug,select_widgets


def get_handlers(halcomp,builder,useropts):

    global debug
    for cmd in useropts:
        exec(cmd, globals())

    set_debug(debug)

    return [HandlerClass(halcomp, builder, useropts)]
