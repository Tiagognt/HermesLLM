# DAPT Dataset for the  HERMES-LLM 

This repository contains the data collection and formatting pipeline used to build the training corpus for the HERMER project. It stores the raw sources, the cleaned JSONL datasets in the following format `{id, source, category, tier, license, url, lang, text, n_tokens,
collected_at}`, and the scripts used to regenerate them.

## Structure of the repository

```text
HermesLLM/
├── README.md # The file you are reading
├── requirement.txt # Required packages for the python scripts
├── data/
│   ├── clean/
│   │   ├── cat1/ # Clean data corpus for the category 1
│   │   ├── cat2/ # Clean data corpus for the category 2
│   │   └── cat3/ # Clean data corpus for the category 3
│   └── raw/ # raw datas collected accros many sources
│       ├── urdf/
│       └── vendors_manuals_pdf/
└── scripts/
    ├── pdf_formater.py
    ├── token_counter.py
    ├── urdf_collector.py
    ├── urdf_formater.py
    └── urdf_parser.py
```

The data is organized into 3 categories:

| Category | Data type | Source |
| --- | --- | --- |
| 1 | General robot data | Clean corpus stored in `data/clean/cat1/` |
| 2 | Task planning | Clean corpus stored in `data/clean/cat2/` |
| 3 | URDF and robot specs | Built from `data/raw/vendors_manuals_pdf/` and `data/raw/urdf/`, then exported to `data/clean/cat3/` |

## Setup the repo

To rerun the scripts and regenerate the datasets, create a virtual environment and install the Python dependencies:

```bash
python3 -m venv .env
source .env/bin/activate
pip install -r requirement.txt
```

You may also need `pdftotext` available on your system for the PDF pipeline.

## Script usage

Run the scripts from the `scripts/` directory so the relative paths resolve correctly:

```bash
cd scripts/
```

### Token counting

`token_counter.py` reports the token count for each category, the total token count across the cleaned corpora and the token repartition among the 3 categories.

```bash
python3 token_counter.py
```

### Script description

Scripts starting with `pdf` format the content of the vendor manuals that were manually downloaded and placed in `data/raw/vendors_manuals_pdf/`.

Scripts starting with `urdf` form the pipeline used to fetch, parse, and format URDF files from GitHub repositories and the `robot_descriptions.py` package.

To rebuild the Category 3 corpus, run:

```bash
python3 pdf_formater.py
python3 urdf_formater.py
```

`urdf_formater.py` may take some time because it can download and parse many URDF files.

## Note about the use of claude

To be honest, claude help me to build this data-set.
I chosed to do things more manually for the Cat 3 by trying to create the pipeline on my own and claude help me to use tools I have never used and also correct bugs.
For the Cat 1 & 2, claude was more efficient to collect things on his own so that is why there are no script for those categories.