from model.mod_pifold import InverseFoldingDiffusionPiFoldModel
import os
import torch
from data.dataset import RLDIFDataset
from torch.utils.data import DataLoader
from utils.utils import load_config, featurize_GTrans, mpnn_index_to_AA, slice_dict, calculate_diversity, Config
from tqdm import tqdm
import numpy as np
import pandas as pd
import esm
from transformers import AutoTokenizer
from model.protein_mpnn import ProteinMPNN
#from run.trainer import train
from torch.utils.data import DataLoader
#import logomaker #n.b commeted out 
import shutil
import matplotlib.pyplot as plt
import pickle
from torch.utils.data import WeightedRandomSampler
from torch.utils.data import Sampler
import random
import pickle as pkl

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

#n.b. added for different sampling methods
class ReversedSampler(Sampler):
    def __init__(self, base_sampler):
        self.base_sampler = list(base_sampler)

    def __iter__(self):
        return iter(reversed(self.base_sampler))

    def __len__(self):
        return len(self.base_sampler)
    
class RandSampler(Sampler):
    def __init__(self, base_sampler):
        self.base_sampler = list(base_sampler)

    def __iter__(self):
        return iter(sorted(self.base_sampler, key=lambda _: random.random()))

    def __len__(self):
        return len(self.base_sampler)

def test(config, model, dataloader, split_name, foldfunction = None):

    if config.protein_mpnn:
        index_to_AA = mpnn_index_to_AA
    elif config.rldif or config.dif_large:
        alphabet = "ACDEFGHIKLMNPQRSTVWY"
        index_to_AA = {i: a for i, a in enumerate(alphabet)}
    elif config.esmif:
        index_to_AA = AutoTokenizer.from_pretrained("facebook/esm2_t33_650M_UR50D")
        valid_indices = index_to_AA.encode('ARNDCQEGHILKMFPSTWYV')[1:-1]
        alphabet='ARNDCQEGHILKMFPSTWYV'
        mask_token = []
        bad_tokens = []
        for token, idx in index_to_AA.get_vocab().items():
            if idx not in valid_indices:
                mask_token.append(idx)
                bad_tokens.append(token)

    results = []

    per_batch_accuracy = []

    per_batch_tm_vec_output = []
    per_batch_tm_scores = []

    for batch in tqdm(dataloader):

        for i in range(config.num_samples):
            if config.protein_mpnn:
                names = batch["name"]
                batch = slice_dict(
                    batch,
                    keys=[
                        "X",
                        "S",
                        "mask",
                        "chain_M",
                        "residue_idx",
                        "chain_encoding_all",
                    ],
                )

                batch["decoding_order"] = torch.arange(torch.prod(torch.tensor(batch["chain_M"].shape))).reshape(batch["chain_M"].shape).to(device)

                sample_args = {**batch}

                if config.free_positions:
                    pos_unfixed_mask = []
                    S_true = batch["S"]
                    for pos in range(S_true.shape[1]):
                        if pos in config.free_positions:
                            pos_unfixed_mask.append(1)
                        else:
                            pos_unfixed_mask.append(0)
                    sample_args["pos_unfixed_mask"] = torch.tensor(pos_unfixed_mask).to(device)

                if bool(config.temp):
                    sample_args['temperature'] = config.temp
                else:
                    sample_args["decoding_order"] = torch.rand(batch["chain_M"].shape).to(device)
                    sample_args['temperature'] = 0.000000000001
                    
                samples = model.simplest_sample(**sample_args)

                out = {}
                out["features_0_step"] = samples["S"]
                out["features_true"] = batch["S"]
                out["mask"] = batch["mask"]
                batch["name"] = names
            elif config.rldif or config.dif_large:
                out = model.sample(batch.clone().to(device), closure=True)
                names = batch["names"]
            elif config.esmif:
                coords = batch['X'][:,:,:3, :]
                pred_sequences = []
                true_seq = [i for i in index_to_AA.decode([str(i.item()) for i in list(batch['S'][0])])][::2]
                
                for i in coords:
                    if bool(config.free_positions):
                        fixedprot = []
                        for pos in range(len(true_seq)):
                            if pos in config.free_positions:
                                fixedprot.append('<mask>')
                            else:
                                fixedprot.append(true_seq[pos])

                        res = model.sample(i, partial_seq = fixedprot, temperature = 1.0)
                    else:
                        res = model.sample(i, temperature = 1.0)
                    pred_sequences.append(index_to_AA.encode(res)[1:-1])

                out = {}
                out['features_0_step'] = torch.stack([torch.tensor(i) for i in pred_sequences])
                out['features_true'] = batch['S']
                out['mask'] = batch['mask']
                names = batch['name']
            else:
                out = model.sample(batch.clone().to(device), closure=True)
                names = batch["names"]

            accs = []
            tm_vec_res = []
            counter = 0
            num = 0
            for ft, fp, mask, name in zip(
                out["features_true"],
                out["features_0_step"],
                out["mask"],
                names,
            ):
                if config.protein_mpnn or config.esmif:
                    mask = mask.to(torch.bool)
                else:
                    mask = mask.astype(bool)
                
                fp, ft = fp[mask], ft[mask]

                n = ft.shape[0]

                if config.protein_mpnn or config.esmif:
                    acc = (ft == fp).sum(axis=-1).sum() / float(n)
                    if config.esmif:
                        pred_sequence= "".join(index_to_AA.decode(fp).split(" "))
                        real_sequence = "".join(index_to_AA.decode(ft).split(" "))
                        for l in bad_tokens:
                            if l in pred_sequence:
                                pred_sequence = pred_sequence.replace(l, 'A')
                            if l in real_sequence:
                                real_sequence = real_sequence.replace(l, 'A')
                    else:
                        mpnn_alphabet = "ACDEFGHIKLMNPQRSTVWYX"
                        pred_sequence = "".join([mpnn_alphabet[i] for i in fp])
                        real_sequence = "".join([mpnn_alphabet[i] for i in ft])

                    coordinates_res = batch["X"][batch["name"].index(name)]
                    mask_res = batch["mask"][batch["name"].index(name)].bool()
                else:
                    acc = (
                        ft.argmax(axis=-1) == fp.argmax(axis=-1)
                    ).sum() / float(n)
                    ft = ft.argmax(axis=-1)
                    fp = fp.argmax(axis=-1)

                    pred_sequence = "".join(
                        np.vectorize(index_to_AA.get)(fp).tolist()
                    )
                    real_sequence = "".join(
                        np.vectorize(index_to_AA.get)(ft).tolist()
                    )

                    if "name" not in batch:
                        coordinates_res = batch["x"][
                            batch["batch"] == batch["names"].index(name)
                        ]
                        mask_res = batch["mask"][
                            batch["batch"] == batch["names"].index(name)
                        ]
                    else:
                        coordinates_res = batch["x"][
                            batch["batch"] == batch["name"].index(name)
                        ]
                        mask_res = batch["mask"][
                            batch["batch"] == batch["name"].index(name)
                        ]

                accs.append(acc)

                if foldfunction is not None:
                    tm_scores = foldfunction(pred_sequence, real_sequence)
                    print(tm_scores)
                else:
                    tm_scores = None

                results.append(
                    {
                        "name": name,
                        "pred": pred_sequence,
                        "real": real_sequence,
                        "tm_score": tm_scores,
                        "split_name": split_name,
                    }
                )

                num += 1
        
        if type(accs[0]) is torch.Tensor:
            accs = [i.cpu().numpy() for i in accs]
        acc = np.mean(accs)
        print(f"Accuracy: {acc}")

        if tm_scores is not None:
            tm_scores = np.mean(tm_scores)
        else:
            print(f"TM-Score Output: {tm_scores}")
 
        per_batch_accuracy.append(acc)
        per_batch_tm_scores.append(tm_scores)

    print(f"Average Accuracy: {np.mean(per_batch_accuracy)}")
    if foldfunction is not None:
        print(f"Average TM-Score: {np.mean(per_batch_tm_scores)}")

    df = pd.DataFrame(results)
    if config.docker:
        pdb_base_path = os.environ.get('PDB_BASE_PATH', '/usr/src/app/input_files/')
        df.to_csv(pdb_base_path + str(config.name) + "_results.csv")
    else:
        df.to_csv(str(config.name) + "_results.csv")
        pdb_base_path = './'

    for name in df['name'].unique():
        if os.path.exists(pdb_base_path + name):
            shutil.rmtree(pdb_base_path + name)
        os.mkdir(pdb_base_path + name)
        sequences = df[df['name'] == name]["pred"].values
        with open(pdb_base_path + name + "/diversity", "w") as f:
            f.write(str(calculate_diversity(sequences)))

        max_length = max(len(seq) for seq in sequences)

        # for start in range(0, max_length, 100):
        #     chunk = [seq[start:start+100] for seq in sequences if len(seq) > start]
        #     sequence_df = logomaker.alignment_to_matrix(chunk)
            
        #     # Create the sequence logo
        #     fig, ax = plt.subplots(figsize=(100, 5))
        #     logo = logomaker.Logo(sequence_df, ax=ax)
        #     logo.style_spines(visible=False)
        #     logo.style_spines(spines=('left', 'bottom'), visible=True)
        #     logo.ax.set_ylabel('Frequency')
        #     plt.savefig(f"{pdb_base_path}{name}/chunk_{start//100}_sequence_logo.png", dpi=300, bbox_inches='tight')
        #     plt.show()

if __name__ == '__main__':
    args = load_config('./configs/config.yaml')

    if args.docker is True:
        pdb_base_path = os.environ.get('PDB_BASE_PATH', '/usr/src/app/input_files/')
        args = load_config(pdb_base_path + 'config.yaml')
        args.data.custom_pdb_input = pdb_base_path + args.data.custom_pdb_input
        args.data.docker = True
    else:
        args.data.docker = False

    if sum([args.rldif, args.dif_large, args.esmif, args.protein_mpnn]) != 1:
        raise ValueError("Exactly one model must be selected.")

    if args.rldif is True or args.dif_large is True:
        if args.dif_large:
            args.pifold_model.network.num_encoder_layers = 20
        args.pifold_model.free_positions = args.free_positions
        model = InverseFoldingDiffusionPiFoldModel(args.pifold_model).to(device)
        
        if args.dif_large:
            #dowload and loads orginal RLDIF large ckpt. 
            if not os.path.exists('RLDIF_8M.ckpt'):
                os.system("wget https://zenodo.org/records/14509073/files/RLDIF_8M.ckpt")

             #old m_path = RLDIF_8M.ckpt
            if args.inference and args.m_name:
                m_path = args.m_name
            else:
                m_path = 'RLDIF_8M.ckpt' #orgnal n.b
            state_dict = torch.load(m_path, map_location=device)['state_dict'] #n.b added map_location
        else:
            #old m_path = last.ckpt
            if args.inference and args.m_name:
                m_path = args.m_name
            else:
            #Downloads the base rld weights
                if not os.path.exists('last.ckpt'):
                    os.system('wget https://zenodo.org/records/11304952/files/last.ckpt')
                    m_path = 'last.ckpt' #orgnal n.b
            state_dict = torch.load(m_path, map_location=device)['state_dict'] #n.b added map_location 

        new_state_dict = {}
        for k, v in state_dict.items():
            new_state_dict[k.replace('model.', '')] = v
        model.load_state_dict(new_state_dict)
    elif args.esmif is True:
        model, alphabet = esm.pretrained.esm_if1_gvp4_t16_142M_UR50()
    elif args.protein_mpnn is True:
        args.model_mpnn.k_neighbors = 38
        model = ProteinMPNN(args.model_mpnn).to(device) 
        if not os.path.exists('protein_mpnn_checkpoint.ckpt'):
            os.system('wget https://zenodo.org/records/14509073/files/protein_mpnn_checkpoint.ckpt')
        checkpoint = torch.load('protein_mpnn_checkpoint.ckpt')
        ckpt_dict_new = dict()
        for k in checkpoint["state_dict"].keys():
            res = k.replace("model.mpnn.", "")
            ckpt_dict_new[res] = checkpoint["state_dict"][k]
        model.load_state_dict(ckpt_dict_new)
    
    args.data.rldif = args.rldif
    args.data.protein_mpnn = args.protein_mpnn

    if args.inference:
        model = model.eval()
        #n.b. option to load pkl file
        if args.data.load_pkl:
            with open(args.data.load_pkl, 'rb') as f:
                dataset = pkl.load(f) 
        else:
            dataset = RLDIFDataset(args.data)

        if args.rldif or args.dif_large:
            collate_function = model.collate_fn
        elif args.esmif:
            collate_function = featurize_GTrans
        elif args.protein_mpnn:
            collate_function = dataset.collate_fn


        dataloader = DataLoader(
                    dataset,
                    batch_size=64, #n.b chagned
                    shuffle=False,
                    collate_fn=collate_function,
                )

        
        test(args, model, dataloader, args.data.split_name)