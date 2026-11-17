"""Build actual Uno firmware with the locally installed Arduino AVR toolchain.
No uploads; no edits to the user's installed core or libraries.
"""
import concurrent.futures, os, pathlib, subprocess, zipfile, argparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--arduino-data', type=pathlib.Path, default=pathlib.Path.home()/'AppData/Local/Arduino15')
ARDUINO = parser.parse_args().arduino_data
CORE = ARDUINO / 'packages/arduino/hardware/avr/1.8.8'
BIN = ARDUINO / 'packages/arduino/tools/avr-gcc/7.3.0-atmel3.6.1-arduino7/bin'
BUILD = ROOT / '.build'
BUILD.mkdir(exist_ok=True)
LIBS = BUILD / 'libraries'
LIBS.mkdir(exist_ok=True)
for name in ('U8g2-2.36.19.zip', 'DHT_sensor_library-1.4.7.zip',
             'Adafruit_Unified_Sensor-1.1.15.zip', 'Adafruit_NeoPixel-1.15.5.zip'):
    with zipfile.ZipFile(ARDUINO / 'staging/libraries' / name) as z:
        for member in z.infolist():
            target = (LIBS / member.filename).resolve()
            if not target.is_relative_to(LIBS.resolve()):
                raise ValueError(member.filename)
        z.extractall(LIBS)

def run(args):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True, errors='replace')
    if p.returncode:
        raise RuntimeError(' '.join(map(str,args))+'\n'+p.stdout+p.stderr)
    return p.stdout+p.stderr

includes = [CORE/'cores/arduino', CORE/'variants/standard']
lib_sources=[]
for lib in LIBS.iterdir():
    folder = lib/'src' if (lib/'src').exists() else lib
    includes.append(folder)
    candidates=folder.rglob('*') if folder.name=='src' else folder.iterdir()
    lib_sources.extend(p for p in candidates if p.suffix in ('.c','.cpp','.S'))
servo=ARDUINO/'libraries/Servo/src'
includes.append(servo)
lib_sources += list((servo/'avr').glob('*.cpp'))
for lib in ('Wire','SPI'):
    folder=CORE/'libraries'/lib/'src'
    includes.append(folder)
    lib_sources.extend(p for p in folder.rglob('*') if p.suffix in ('.c','.cpp','.S'))

common=['-Os','-g','-ffunction-sections','-fdata-sections','-flto','-mmcu=atmega328p',
        '-DF_CPU=16000000UL','-DARDUINO=10819','-DARDUINO_AVR_UNO','-DARDUINO_ARCH_AVR','-Wall','-Wextra']
inc=['-I'+str(p) for p in includes]

def compile_one(job):
    source,obj=job
    is_cpp=source.suffix in ('.cpp','.ino')
    flags=['-std=gnu++11','-fpermissive','-fno-exceptions','-fno-threadsafe-statics','-Wno-error=narrowing'] if is_cpp else ['-std=gnu11','-fno-fat-lto-objects']
    if source.suffix=='.S': flags=['-x','assembler-with-cpp']
    if source.suffix=='.ino': flags+=['-x','c++']
    log=run([BIN/('avr-g++.exe' if is_cpp else 'avr-gcc.exe'),*common,*flags,*inc,'-c',source,'-o',obj])
    return log

def archive(name,sources):
    dest=BUILD/name
    dest.mkdir(exist_ok=True)
    jobs=[(p,dest/(str(i)+'.o')) for i,p in enumerate(sources)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        logs=list(pool.map(compile_one,jobs))
    archive_path=dest/(name+'.a')
    if archive_path.exists(): archive_path.unlink()
    run([BIN/'avr-gcc-ar.exe','rcs',archive_path,*[obj for _,obj in jobs]])
    (dest/'warnings.txt').write_text(''.join(logs),encoding='utf-8')
    print(f'Built {name}: {len(jobs)} translation units',flush=True)
    return archive_path

core_sources=[p for p in (CORE/'cores/arduino').iterdir() if p.suffix in ('.c','.cpp','.S')]
core_archive=archive('core',core_sources)
lib_archive=archive('libs',lib_sources)
out=ROOT/'compiled';out.mkdir(exist_ok=True)
for board in ('OldBoard_Main','NewBoard_Expansion'):
    source=ROOT/board/(board+'.ino')
    obj=BUILD/(board+'.o')
    log=compile_one((source,obj))
    elf=BUILD/(board+'.elf')
    log+=run([BIN/'avr-gcc.exe','-Os','-g','-flto','-fuse-linker-plugin','-Wl,--gc-sections',
        '-mmcu=atmega328p','-o',elf,obj,lib_archive,core_archive,'-lm'])
    log+=run([BIN/'avr-size.exe','-C','--mcu=atmega328p',elf])
    run([BIN/'avr-objcopy.exe','-O','ihex','-R','.eeprom',elf,out/(board+'.hex')])
    (ROOT/'verification'/('compile_'+board+'.txt')).write_text(log,encoding='utf-8')
    print(board+'\n'+log,flush=True)
