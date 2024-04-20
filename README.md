# Tree 4024 VMC LinuxCNC Machine 
This repository contains the machine configuration for a Tree4024 Vertical Milling Machine.

The configuration works with LinuxCNC 2.9

## Configurations
- [tree_4024.hal config](tree_4024.hal)
- [tree_4024.ini settings](tree_4024.ini)

## Hardware
The machine uses a **Mesa 7i77** as its interface card to read encoder outputs, as well as control the velocity (SPEED) of the servos

The machine is equipped with Yaskawa Servo drives for all 3 linear axis, as well as a Yaskawa controller for the Spindle.

## Mega2560
An IO interface via an `Arduino mega2560` exists written in Python.

This configuration is for making hardware changes to the machine and testing that those configurations do not destroy or circuitry.
The arduino is protected by a series of optocoupler boards, but breaking the arduino is not a costly mistake.

The Mega2560 can be configured to handle all digital (binary) input and output, but SHOULD NOT be used in for actual machining work.

