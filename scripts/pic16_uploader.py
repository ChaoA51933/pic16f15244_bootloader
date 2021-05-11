#***********************************************************************************************************************
# File Name       : app_uploader.c
# Description     :
# Original Author : Chao Wang
# Created on      : April 12, 2021, 1:37 PM
#***********************************************************************************************************************
from __future__ import print_function
import sys

try:
    import argparse
    from intelhex import IntelHex
    import os
    import serial
    import time  
except ImportError:
    sys.exit("""ImportError: You are probably missing some modules.
To add needed modules, run like 'python -m pip install -U future pyserial intelhex'""")

#-----------------------------------------------------------------------------------------------------------------------
# Generate help and use messages
parser = argparse.ArgumentParser(
    description='Serial bootloader script for Microchip PIC16 family MCUs',
    epilog='Example: pic16_uploader.py ./App/Release/App.hex 0x20000 COM5 9600',
    formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('file', help='Hex file to upload')
parser.add_argument('flashsize', help='Total device flash size based on Byte')
parser.add_argument('comport', help='UART COM port')
parser.add_argument('baudrate', help='UART baud rate')

if len(sys.argv) == 1:
    parser.print_help()
    sys.exit(1)
args = parser.parse_args()

# Command line arguments
File = sys.argv[1]
FlashSize = int(sys.argv[2], 16)
ComPort = sys.argv[3]
Baudrate = int(sys.argv[4], 10)

#-----------------------------------------------------------------------------------------------------------------------
# Variables
CMDRunning = False      # semaphere flag for running commands
Erased = False          # flag for eraseing function
UART = None             # flag for UART open

GoBuf = bytearray()     # global output buffer for functions OutPacket/InCom
RcvBuf = bytearray()    # global input buffer for functions OutPacket/InCom
FBuf = bytearray()

EraseSizeW = 0x20       # erase row size (words), will be update during get version process.
WriteSizeW = 0x20       # Write latches per row size (words), will be update during get version process.

#***********************************************************************************************************************
# Function : hex2bin(hex_file, flash_size)
#***********************************************************************************************************************
def hex2bin(hex_file, flash_size):
    # Load application hex file and convert to bin file
    ih = IntelHex()
    fileextension = hex_file[-3:]
    ih.loadfile(hex_file, format=fileextension)

    appstart = ih.minaddr()
    # print("\n", "Start Address: %#06x" % (appstart))

    start_app = ih.tobinarray(end=flash_size - 1)
    bin_start_file = os.path.splitext(hex_file)[0] + ".bin"

    # Save original file
    fq = open(bin_start_file, 'wb')
    fq.write(start_app)
    fq.close()

    return appstart

#***********************************************************************************************************************
# Function : out_packet()
#***********************************************************************************************************************
def out_packet():  # STX(0x55)+  General Command Format
    global GoBuf

    GoBuf.insert(0, 0x55)  # STX
    UART.write(GoBuf)

#***********************************************************************************************************************
# Function : in_com(timeout)
#***********************************************************************************************************************
def in_com(timeout):  # timeout == 0 ==> wait until got data
    global RcvBuf

    RcvBuf = bytearray(b'')
    tStart = time.perf_counter()
    Retry = 3

    while True:
        bdata = UART.read()
        if len(bdata) > 0:
            RcvBuf.extend(bdata)

        elif len(RcvBuf) != 0:
            return len(RcvBuf);

        elif timeout != 0:
            if (time.perf_counter() - tStart) > timeout:  # timeout loop & retry
                if Retry == 0: return 0
                print(
                    "Status: No response in " + str(timeout) + " S," + " re-trying " + str(Retry) + ' more time(s).')
                Retry -= 1
                UART.write(GoBuf)
                tStart = time.perf_counter()

#***********************************************************************************************************************
# Function : execute_result(TOut)
#***********************************************************************************************************************
def execute_result(TOut):
    global CMDRunning, GoBuf

    out_packet()

    if in_com(TOut) == 0:
        #Update_Status("No response error, Process terminated !!")
        print("No response error, Process terminated !")
        CMDRunning = False
        return False

    if GoBuf[1] != 0x00 and GoBuf[1] != 0x08 and GoBuf[1] != 0x09 and RcvBuf[10] != 1:
        if RcvBuf[10] == 0xFE:
            print("ADDRESS OUT OF RANGE ERROR when executing command %0X !!" % GoBuf[1])
        if RcvBuf[10] == 0xFF:
            print("Invalid Command ERROR when executing command %0X !!" % GoBuf[1])
        else:
            print("Unknown ERROR when executing command %0X !!" % GoBuf[1])
        CMDRunning = False
        return False

    return True

#***********************************************************************************************************************
# Function : open_uart()
#***********************************************************************************************************************
def open_uart():
    global UART

    if UART == None:
        try:
            UART = serial.Serial(ComPort, baudrate=Baudrate, timeout=1)
            UART.reset_input_buffer()
        except:
            print('Status: ' + 'open ' + ComPort + ' fail!!')
            return False
    return True

#***********************************************************************************************************************
# Function : get_version()
#***********************************************************************************************************************
def get_version():
    global GoBuf, EraseSizeW, WriteSizeW
    
    print("*******************Read Version Command...*******************\n")
    print("Hint: Getting version ...\n")

    GoBuf = bytearray(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    
    
    print("Tx ->", GoBuf.hex(' '), "\n")

    
    if execute_result(1.0) == False: sys.exit(1)
    print("Rx ->", RcvBuf.hex(' '), "\n")
    
    FWInfo = RcvBuf[10:]

    EraseSizeW = FWInfo[10]
    WriteSizeW = FWInfo[11]

    print("Status: Get version completely", 'successful!\n')
    print("*************************************************************\n")

#***********************************************************************************************************************
# Function : erase_flash(MinAddr, MaxAddr, RowSize)
# Note     ：every parameter is based on bytes...
#***********************************************************************************************************************
def erase_flash(MinAddr, MaxAddr, RowSize):
    global GoBuf, Erased

    
    print("*******************Erase Flash Command...********************\n")
    print("Hint: Erasing flash ...\n")
    
    EraseCnt = int((MaxAddr - MinAddr) / RowSize)

    # Only for Erase command of PIC16F1_bootload.c
    GoBuf = bytearray(b'\x03') + EraseCnt.to_bytes(2, byteorder='little') + bytearray(b'\x55\xaa') + (
                MinAddr >> 1).to_bytes(4, byteorder='little')
    print("Tx ->", GoBuf.hex(' '), "\n")                

    if execute_result(10.0) == False: sys.exit(1)
    print("Rx ->", RcvBuf.hex(' '), "\n")

    print("Status: Erase flash memory", 'successful!\n')
    print("*************************************************************\n")    

#***********************************************************************************************************************
# Function : write_flash(MinAddr, MaxAddr, RowSize)
#***********************************************************************************************************************
def write_flash(MinAddr, MaxAddr, RowSize):
    global FBuf, File, GoBuf

    print("*******************write Flash Command...********************\n")
    print("Hint: Writing flash ...\n")

    bin_file = os.path.splitext(File)[0] + ".bin"
    size = os.path.getsize(bin_file);
    print("Uploading", size, "bytes from bin file...\n")

    with open(bin_file, "rb") as f:
        FBuf += f.read()

    EmptyArray = bytearray(b'\xff' * RowSize)

    for Address in range(MaxAddr - RowSize, MinAddr - RowSize, -RowSize):
        # Only for Write command of PIC16F1_bootload.c
        GoBuf = bytearray(b'\x02') + RowSize.to_bytes(2, byteorder='little') + bytearray(b'\x55\xaa') + (
                Address >> 1).to_bytes(4, byteorder='little')
        if EmptyArray == FBuf[Address - MinAddr: Address - MinAddr + RowSize]:
            continue

        GoBuf += FBuf[Address - MinAddr: Address - MinAddr + RowSize]

        print("Programming range from 0X%08XH to 0X%08XH. (Whole range is from 0X%08Xh to 0X%08Xh)"
              % (Address, Address + RowSize - 1, MinAddr, MaxAddr - 1), '...\n')
        print("Tx ->", GoBuf.hex(' '), "\n") 

        if execute_result(10.0) == False:
            sys.exit(1)
        print("Rx ->", RcvBuf.hex(' '), "\n")

    print("Status: Writing flash memory successfully !!  Range from 0X%08Xh to 0X%08Xh.\n" % (MinAddr, MaxAddr - 1))
    print("*************************************************************\n")

#***********************************************************************************************************************
# Function : calculate_checksum(MinAddr)
#***********************************************************************************************************************
def calculate_checksum(MinAddr):
    global FBuf, File, GoBuf

    print("****************Calculate Checksum Command...****************\n")
    print("Hint: calculate checksum ...\n")

    bin_file = os.path.splitext(File)[0] + ".bin"
    size = os.path.getsize(bin_file);

    with open(bin_file, "rb") as f:
        FBuf += f.read()

    checksum = 0
    for Address in range(0, size, 2):
        checksum += FBuf[Address]
        checksum +=((FBuf[Address+1]&0x3f)<<8)
    checksum &= 0xFFFF

    GoBuf = bytearray(b'\x08') + size.to_bytes(2, byteorder='little') + bytearray(b'\x55\xaa') + (
            MinAddr>>1).to_bytes(4, byteorder='little')
    print("Tx ->", GoBuf.hex(' '), "\n") 

    if execute_result(10.0) == False: sys.exit(1)
    print("Rx ->", RcvBuf.hex(' '), "\n")

    checksum_received = (RcvBuf[10]+(RcvBuf[11]<<8))

    if checksum != checksum_received:
        print("Status: Calculate checksum fail!\n")
        sys.exit(1)
    else:
        print("Status: Calculate checksum successful!\n")
    print("*************************************************************\n")        
#***********************************************************************************************************************
# Function : reset_device()
#***********************************************************************************************************************
def reset_device():
    global GoBuf

    print("*******************Reset Device Command...*******************\n")    
    print("Hint: reset device ...\n")

    GoBuf = bytearray(b'\x09\x00\x00\x55\xaa\x00\x00\x00\x00')
    print("Tx ->", GoBuf.hex(' '), "\n") 
    
    if execute_result(1.0) == False: sys.exit(1)
    print("Rx ->", RcvBuf.hex(' '), "\n")

    if RcvBuf[10] != True:
        print("Status: Reset device fail!\n")
        sys.exit(1)
    else:
        print("Status: Reset device successful!\n")
    print("*************************************************************\n")        


#***********************************************************************************************************************
# Function : main
#***********************************************************************************************************************
if __name__ == "__main__":
    os.system('')
    print("\033[1;34;40m")
    if open_uart() == True:
        print("**********************BOOTLOAD START*************************\n")    
        APPStartAddr = hex2bin(File, FlashSize)
        get_version()
        erase_flash(APPStartAddr, FlashSize, (EraseSizeW<<1))
        write_flash(APPStartAddr, FlashSize, (WriteSizeW<<1))
        calculate_checksum(APPStartAddr)
        reset_device()
        print("*********************BOOTLOAD COMPLETE***********************\n")     
        sys.exit(1)
    else:
        sys.exit(1)
    print("\033[0m") 