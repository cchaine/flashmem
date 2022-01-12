#!/usr/bin/env python3
from pyftdi.spi import *
import sys
from time import sleep

def get_status():
    return slave.exchange([0x9F], 1)

if len(sys.argv) != 2:
    print("Usage: {} bin_file".format(sys.argv[0]))
    exit(1)

conf_bin_file = open(sys.argv[1], "rb")
conf_bin = conf_bin_file.read()
conf_bin_file.close()

spi = SpiController()
spi.configure("ftdi://ftdi:232h/0")
slave = spi.get_port(cs=0, freq=1e4, mode=3)

jedec_id = slave.exchange([0x9F], 2)
if jedec_id != 0x2020:
    print("Failed to detect M25P16 Flash memory");
    exit()

# Write enable
slave.exchange([0x06])
# Check if write enable worked
read_status = slave.exchange([0x05], 1)
if read_status & 0x2 == 0:
    print("Failed to enable write")
    exit()

pages = [conf_bin[i:i+256] for i in range(0, len(conf_bin), 256)]

# Write file
address = 0
for page in pages:
    # Check if the flash is ready
    while get_status() & 0x1 == 1:
        sleep(0.01)
    
    page_write = [0x02]
    page_write += [(address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]
    page_write += page
    slave.exchange(page_write)

    # Increment address
    address += len(page)

# Read back
address = 0
equal = True
for page in pages:
   read_page = slave.exchange([0x0B, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF], len(page))
   for i in range(len(page)):
       if page[i] != read_page[i]:
           print("Written page {} differs".format(i))
           equal = False
    address += len(page)

if equal:
    print("Flash successfull!")
