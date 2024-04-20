from __future__ import print_function

import sys
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import hal
import gtk
import gobject
from gladevcp.hal_meter import HAL_Meter
from gladevcp.led import HAL_LED
from gladevcp.hal_bar import HAL_HBar


class HBar(HAL_HBar):

    def __init__(self):
        super(HBar, self).__init__()
        # here because class is throwing error saying it doesn't have these attrs
        self.force_width = 20
        self.force_height = 20


class SpindleDisplay(gtk.ScrolledWindow):
    HAL_COMPONENT_NAME = 'spindleui'
    UPDATE_FREQUENCY_MILLIS = 10

    PIN_SPINDLE_RPM = 'spindle-rpm'
    PIN_TARGET_RPM = 'commanded-rpm'
    PIN_SPEED_ATTAINED = 'speed-attained'

    def __init__(self, pyvcp):
        # member variables
        super(SpindleDisplay, self).__init__()
        self.set_size_request(300, 300)
        self._update_loop = False  # is the update loop running?
        hal_component = hal.component(self.HAL_COMPONENT_NAME)
        self._hal_component = hal_component
        hal_component.newpin(self.PIN_SPINDLE_RPM, hal.HAL_FLOAT, hal.HAL_IN)
        hal_component.newpin(self.PIN_TARGET_RPM, hal.HAL_FLOAT, hal.HAL_IN)
        hal_component.newpin(self.PIN_SPEED_ATTAINED, hal.HAL_BIT, hal.HAL_IN)
        hal_component.ready()

        self._container = gtk.VBox()
        self.add_with_viewport(self._container)
        self.set_border_width(0)
        self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.set_shadow_type(gtk.SHADOW_NONE)

        # see http://linuxcnc.org/docs/html/gui/gladevcp.html
        self._rpm_current_lbl = gtk.Label('CURRENT RPM')
        self._rpm_target_lbl = gtk.Label('TARGET RPM')
        self._rpm_atspeed_lbl = gtk.Label('SPEED ATTAINED')
        self._rpm_atspeed_led = HAL_LED()
        self._rpm_current_bar = HBar()
        self._rpm_target_bar = HBar()
        self._rpm_meter = HAL_Meter()

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

        rpm_target_box = gtk.HBox()
        rpm_current_box = gtk.HBox()
        rpm_atspeed_box = gtk.HBox()

        for bar in (self._rpm_current_bar, self._rpm_target_bar):
            bar.set_property('min', 0.0)
            bar.set_property('max', 8000.0)
            bar.set_property('bg_color', gtk.gdk.color_parse('white'))
            bar.set_property('force_width', 150)
            bar.set_property('force_height', 25)

        rpm_current_box.pack_start(self._rpm_current_lbl, expand=False, fill=False, padding=0)
        rpm_current_box.pack_start(self._rpm_current_bar, expand=True, fill=True, padding=0)

        rpm_target_box.pack_start(self._rpm_target_lbl, expand=False, fill=False, padding=0)
        rpm_target_box.pack_start(self._rpm_target_bar, expand=True, fill=True, padding=0)

        led = self._rpm_atspeed_led
        led.set_property('on_color', gtk.gdk.color_parse('green'))
        led.set_property('off_color', gtk.gdk.color_parse('red'))
        led.set_property('led_shape', 2)  # SQUARE
        rpm_atspeed_box.pack_start(self._rpm_atspeed_lbl, expand=False, fill=False, padding=0)
        rpm_atspeed_box.pack_start(self._rpm_atspeed_led, expand=True, fill=True, padding=0)

        meter = self._rpm_meter
        meter.set_property('label', 'Spindle RPM')
        meter.set_property('min', 0.0)
        meter.set_property('max', 100.0)
        meter.set_property('force_size', 120)
        meter.set_property('bg_color', gtk.gdk.color_parse('white'))

        self._container.pack_start(rpm_current_box, expand=False, fill=False)
        self._container.pack_start(rpm_target_box, expand=False, fill=False)
        self._container.pack_start(rpm_atspeed_box, expand=False, fill=False)
        self._container.pack_end(meter, expand=True, fill=True, padding=0)

        self.show_all()
        if not self._update_loop:
            self.start_updates()

    def update(self):
        """
        Apply hal pin status to buttons, updating their visual representation based on pin value
        """
        log.debug('updating pin states')
        # read pin value / set pin value
        spindle_rpm = self._hal_component[self.PIN_TARGET_RPM]
        target_rpm = self._hal_component[self.PIN_TARGET_RPM]
        spindle_percent = (spindle_rpm / 8000.0) * 100 if spindle_rpm else 0
        speed_attained = self._hal_component[self.PIN_SPEED_ATTAINED]
        self._rpm_target_bar.set_value(target_rpm)
        self._rpm_current_bar.set_value(spindle_rpm)
        self._rpm_meter.set_value(spindle_percent)
        self._rpm_atspeed_led.set_active(speed_attained)
        return True


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

        self.main(window)

    def main(self, window):
        self.panel = SpindleDisplay(self.halcomp)
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
    """
    Called by linuxcnc to initialize this gladevcp plugin!

    :param halcomp:
    :param builder:
    :param useropts:
    :return:
    """
    return [HandlerClass(halcomp, builder, useropts)]


def main():
    window = gtk.Window()
    window.set_title("Spindle")
    window.set_position(gtk.WIN_POS_CENTER)
    window.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('#292929'))
    panel = SpindleDisplay(window)
    window.add(panel)


if __name__ == '__main__':
    sys.exit(main())