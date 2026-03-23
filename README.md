# tal_sampler_preset_gen
code to generate tal sampler preset from multi wav samples


## usage

### tal_preset_gen

generate single instrument from a collection of wav file formatted like ```Bass_C3.wav``` or ```Bass_C3_vel80.wav```
```bash
options:
  -h, --help            show this help message and exit
  --folder FOLDER
  --samples SAMPLES [SAMPLES ...]
  --out OUT
  --pattern PATTERN
  --middle-c MIDDLE_C
  --copy-samples
  --on-duplicate {error,keep-first,keep-last}
  --low-spread LOW_SPREAD
  --high-spread HIGH_SPREAD
```

### batch_tal_preset_gen_from_slice
batch generation of tal sampler presets instruments from a collection of wav file which each contains all notes. 
Notes are manually provided in a text file
```bash 
usage: tal_preset_batch_from_slice4.py [-h] --inputs INPUTS [INPUTS ...] [--out OUT] --config CONFIG [--middle-c MIDDLE_C] [--low-spread LOW_SPREAD] [--high-spread HIGH_SPREAD]

Create TAL Sampler presets from multi-note WAV files.

options:
  -h, --help            show this help message and exit
  --inputs INPUTS [INPUTS ...]
  --out OUT             Optional output root
  --config CONFIG
  --middle-c MIDDLE_C
  --low-spread LOW_SPREAD
  --high-spread HIGH_SPREAD
```
