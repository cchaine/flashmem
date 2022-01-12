#!/usr/bin/env python3
import pyftdi
from pyftdi.spi import *
import sys
from time import sleep
from rich.progress import *
from rich.console import Console
from rich.spinner import *
from rich.theme import Theme

SECTOR_SIZE = 0x10000

def get_status():
    return slave.exchange([0x9F], 1)

def wait_done():
    while (get_status()[0] == 0) or (get_status()[0] & 0x1) == 1:
        continue

if __name__ == "__main__":
    console = Console(theme = Theme({
        "progress.data.speed":"none",
        "progress.percentage":"none",
        "progress.download":"bold yellow",
        "bar.complete":"yellow"
    }))

    console.print("""
                  ________           __    __  ___            
                 / ____/ /___ ______/ /_  /  |/  /__  ____ ___ 
                / /_  / / __ `/ ___/ __ \/ /|_/ / _ \/ __ `__ \\
               / __/ / / /_/ (__  ) / / / /  / /  __/ / / / / /
              /_/   /_/\__,_/____/_/ /_/_/  /_/\___/_/ /_/ /_/ 
        
    """, style="bold blue")

    if len(sys.argv) != 2:
        console.print("Usage: {} bin_file".format(sys.argv[0]), style="red")
        exit(1)

    try:
        conf_bin_file = open(sys.argv[1], "rb")
        conf_bin = conf_bin_file.read()
        conf_bin_file.close()
    except FileNotFoundError:
        console.print("Failed to open file [red]{}[/red]".format(sys.argv[1]), style="red")
        exit(1)

    try:
        spi = SpiController()
        spi.configure("ftdi://ftdi:232h/0")
        slave = spi.get_port(cs=0, freq=1e6, mode=3)
    except pyftdi.usbtools.UsbToolsError:
        console.print("Failed to communicate with the FT232H chip", style="red")
        exit(1)

    jedec_id = slave.exchange([0x9F], 2)
    if int.from_bytes(jedec_id, byteorder='big', signed=False) != 0x2020:
        console.print("Failed to detect M25P16 Flash memory", style="red");
        exit(1)

    # Write enable
    slave.exchange([0x06])

    # Check if write enable worked
    read_status = slave.exchange([0x05], 1)
    if read_status[0] & 0x2 == 0:
        console.print("Failed to enable write", style="red")
        exit(1)

    # Disable block protect
    if read_status[0] & 0x1C != 0:
        slave.exchange([0x01, read_status[0] & 0xE3]);

    # Erase
    with Progress(
        SpinnerColumn(spinner_name="point", style="white"),
        TextColumn("[white]{task.fields[name]}", justify="right"),
        BarColumn()
    ) as progress:
        num_sectors = ceil(len(conf_bin) / float(SECTOR_SIZE))
        sectors = [i * SECTOR_SIZE for i in range(num_sectors)]
        erase_progress = progress.add_task("erase", name="Erasing...", total=num_sectors)

        for sector in sectors:
            wait_done()
            slave.exchange([0xD8, (sector >> 16) & 0xFF, (sector >> 8) & 0xFF, sector & 0xFF])
            progress.update(erase_progress, advance=1)

    with Progress(
        SpinnerColumn(spinner_name="point", style="white"),
        TextColumn("[white]{task.fields[name]}", justify="right"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.1f}% -",
        DownloadColumn(),
        "@",
        TransferSpeedColumn(),
        ":",
        TimeRemainingColumn(),
        console=console
    ) as progress:
        pages = [conf_bin[i:i+256] for i in range(0, len(conf_bin), 256)]

        # Write file
        flash_progress = progress.add_task("flash", name="Flashing...", total=len(conf_bin))
        address = 0
        for page in pages:
            # Check if the flash is ready
            wait_done()
            
            page_write = [0x02]
            page_write += [(address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF]
            page_write += page
            slave.exchange(page_write)

            progress.update(flash_progress, advance=len(page))

            # Increment address
            address += 1

        # Verify
        verify_progress = progress.add_task("verify", name="Verifying...", total=len(conf_bin))
        address = 0
        for page in pages:
            wait_done()
            read_page = slave.exchange([0x0B, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF], len(page))
            for i in range(len(page)):
                if page[i] != read_page[i]:
                    console.print("Written page @ {} differs".format(address), style="red")
                    console.print(page.hex())
                    console.print(read_page.hex())
                    exit(1)

            progress.update(verify_progress, advance=len(page))

            address += 1

    console.print("Flash successfull!", style="green")
