
# AntiDIF
Code for AntiDIF **A**ntibody-specific discrete **D**iffusion for **I**nverse **F**olding

From our paper Accurate and Diverse Antibody Specific Inverse Folding with Discrete Diffusion.

Paper link: https://www.biorxiv.org/content/10.1101/2025.07.12.664553v1


AntiDIF is built on top of RL-DIF https://github.com/flagshippioneering/pi-rldif

See tutorial.ipynb for a minimal example walkthrough


# Quick start 

## Install 
### Install with pip or uv (GPU and OLD instructions)

Create and activate venv

```bash
python -m venv .venv

source .venv/bin/activate
```

Install requirements, use either requirements_gpu.txt
for NVidia gpu support or requirements.txt for cpu
only. e.g. gpu

```bash
pip install -r requirements_gpu.txt
```

We then need to install torch-cluster and torch-scatter manually
unfortunately due to some oddity the env may not work break if we t
ry to install these packages in the step above.

for GPU

```bash
pip install torch-scatter --no-build-isolation -f https://data.pyg.org/whl/torch-2.0.0+cu117.html

pip install torch-cluster --no-build-isolation -f https://data.pyg.org/whl/torch-2.0.0+cu117.html

```

for cpu replace with

```bash
pip install torch-scatter --no-build-isolation -f https://data.pyg.org/whl/torch-2.0.0+cpu.html

pip install torch-cluster --no-build-isolation -f https://data.pyg.org/whl/torch-2.0.0+cpu.html
```

### uv install

```bash

uv venv .venv

source .venv/bin/activate

uv pip install -r requirements_gpu.txt

uv pip install torch-scatter --no-build-isolation -f https://data.pyg.org/whl/torch-2.0.0+cu117.html

uv pip install torch-cluster --no-build-isolation -f https://data.pyg.org/whl/torch-2.0.0+cu117.html
```

### Alternative install from RL-DIF

Clone the repo and create an environment (See requirements in RL-DIF, https://github.com/flagshippioneering/pi-rldif)

## Inference on example data
In the pi-rldif-ft directory simply run: 

```bash
python -m run.run
``` 
This will run inference for the example antibody 7yxu.pdb

## Troubleshooting
Absolute paths to m_name and example.csv in config.yaml may need to be set. As well as setting the absolute path to 7yxu.pdb in example.csv.

# Inference with custom inputs and config

config.yaml is where we can control what data to run inference on and more! 
For a full breakdown of the parameters in the config see the RL-DIF readme. Here we focus on the parameters needed for inference with custom inputs. Note, you should only have to change the first two parameters listed below. 
See tutorial.ipynb for more of a walkthrough.

- **custom_pdb_input** (str): 
  Path to CSV file that points to PDB files to run inference for. It is recommended to give absolute paths.

- **m_name** (str):
  Path to AntiDIF model checkpoint, it is recommend to change this to the absolute path the ckpt is in on your machine. 

- **load_pkl** (str)
  Option to load data from pkl file (default null and data is loaded from CSV)
  Path to pkl file of RLDIFDataset, or null for CSV loading.


- **protein_mpnn** (bool):  
  Ensure set to False to run AntiDIF

- **rldif** (bool):  
  Ensure set to True, this loads the rldif architecture that the weights for AntiDIF are then loaded into

- **esmif** (bool):  
  Ensure set to False to run AntiDIF

- **dif_large** (bool):  
  Ensure set to False to run AntiDIF

- **inference** (bool)
  Ensure this is set to True for inference

Note setting dif_large=True or not providing a m_name will load the base RLDIF weights.

## Creating a csv for running inference with custom inputs
 
To run inference on custom inputs, a CSV file that gives the PDB paths is required.
An example of what this CSV file looks like is given by data/raw_data/sab_test_hpc.csv. And data/raw_data/example.csv. Note that the PDB files the CSV points to only have the heavy and light chain of the antibodies thus, the 2nd row (that tells the model what chains to process) for the PDB IDs in the CSV is ‘all‘, indicating that the model will consider all chains in the PDB file. It is recommended that your PDB files be formatted in the same way. As an example, see data/raw_data/7yxu.pdb.

Once you have created your custom CSV set the path to it in config.yaml under custom_pdb_input. Then for inference, from the pi-rldif-ft folder run:

```bash
python -m run.run
``` 
 

# Quick start option 2
Optionally, you can also more closely follow RL-DIF instructions but with AntiDIF weights. model.ckpt gives the model weights for AntiDIF, once this is downloaded the instructions from the RL-DIF github can be followed for inference by simply swapping the RL-DIF checkpoint for model.ckpt in run.py (in this file state_dict should load in the AntiDIF ckpt).
