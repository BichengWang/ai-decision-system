# My Python Notebook

## Motto

Being Honest with Yourself.

## Auth

bichengwang17@gmail.com

## Recommend Env

The recommended running env is conda env to avoid some windows crash or compile issue.

## Directory Structure

In different directory, it would content specific readme file for different code tools.

## Makefile

```shell
python -m pip install --upgrade pip
make env
source venv/bin/activate
make bootstrap
python -m pip install -U pip-tools
pip install -r requirements.txt
```

### Refresh Dependencies

```shell
pip install pip-tools>=4.2.0
pip-compile --no-emit-index-url requirements.in
```

Optional: add current environment full requirements into file

```shell
pip freeze > requirements.txt
```

Checking: check specific lib exist or not

```shell
pip freeze | grep tensorflow-gpu
```

## UV (Ultrafast Python Package Manager)

UV is a fast Python package installer and resolver, written in Rust. It's designed to be a drop-in replacement for pip and virtualenv.

### Installation

```shell
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

### Basic Usage

```shell
# Create a new project
uv init my-project
cd my-project

# Create a virtual environment and install dependencies
uv sync

# Add a dependency
uv add numpy pandas

# Add development dependencies
uv add --dev pytest black

# Run a command in the virtual environment
uv run python script.py

# Activate the virtual environment
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows
```

### Working with pyproject.toml

UV works seamlessly with pyproject.toml files:

```shell
# Install dependencies from pyproject.toml
uv sync

# Install in development mode
uv sync --dev

# Update dependencies
uv sync --upgrade

# Lock dependencies (creates uv.lock)
uv lock
```

### Migration from pip

```shell
# Convert requirements.txt to pyproject.toml
uv pip compile requirements.txt --pyproject

# Or manually add to pyproject.toml dependencies section
dependencies = [
    "numpy",
    "pandas",
    "yfinance",
]
```

### Performance Benefits

- **Fast**: 10-100x faster than pip
- **Reliable**: Deterministic dependency resolution
- **Modern**: Native support for pyproject.toml
- **Compatible**: Works with existing Python tooling

### Advanced Features

```shell
# Install specific versions
uv add "numpy>=1.21.0,<2.0.0"

# Install from git
uv add "git+https://github.com/user/repo.git"

# Install with extras
uv add "requests[security]"

# Show dependency tree
uv tree

# Check for outdated packages
uv sync --upgrade --dry-run
```

## Conda

```shell
brew install --cask anaconda
```

### Create Conda Env

```shell
conda remove -n py-notebook --all
conda create --name py-notebook python=3.12
conda info --envs
activate py-notebook
```

### For M1 specific

install conda in linux or M1
M1 conda: https://github.com/conda-forge/miniforge
https://caffeinedev.medium.com/how-to-install-tensorflow-on-m1-mac-8e9b91d93706
https://developer.apple.com/metal/tensorflow-plugin/

```shell
conda init zsh
conda init bash
conda config --set auto_activate_base false
conda remove -n python-notebook --all
conda create --name python-notebook python=3.9 # must be 3.9
conda info --envs
conda activate python-notebook
conda install causalml
```

then

```shell
conda install -c apple tensorflow-deps
python -m pip install -U tensorflow-macos==2.9
python -m pip install -U tensorflow-metal==0.5.0
conda install pytorch torchvision torchaudio torchdata -c pytorch-nightly
conda install -c conda-forge -y pandas jupyter
pip install tensorflow_datasets
pip install asitop
pip install pytorch-transformers
```

for tensorflow-text special case

```shell
https://developer.apple.com/forums/thread/700906
python -m pip install --ignore-installed ~/Downloads/....whl
```

### For Win specific

install libs for win32

```shell
conda install pywin32
```

### Jupyter notebook

#### lint

```shell
pip install pylint
pip install jupyter_contrib_nbextensions
jupyter contrib nbextension install --user
```

## Git

pruning origin deleted branches

```shell
git remote prune origin
```

git global config for all general commands:

```shell
echo 'alias g=git' >> ~/.zshrc
source ~/.zshrc
g config --global alias.co checkout
g config --global alias.br branch
g config --global alias.amd '!git add -u && git commit --amend --no-edit'
g config --global alias.ci commit
g config --global alias.st status
g config --global alias.ll "log --oneline"
g config --global alias.lg "log --oneline --graph --all --decorate"
g config --global alias.rb "pull --rebase origin"
g config --global alias.sq "rebase -i HEAD~10"
g config --global push.default current
g config --global core.editor "cursor --wait"
g config --global alias.submodule "submodule update --init --recursive"
g config --global alias.dl '!git branch -D $1 && git push --delete origin $1'
g config --global alias.pruning '!git remote prune origin && git gc --prune=now'
g config --global alias.amendpush '!git add . && git commit --amend --no-edit && git push --force origin'
g config --global alias.pr '!f() { git add .; git commit -am "$1"; git rb main && git push origin && gh pr create --title "$1" --body "" --label "auto-merge" --assignees @me; }; f'
g config --global advice.skippedCherryPicks false
g config --global alias.run '!./.git/hooks/pre-run'
g config --global alias.files '!git --no-pager diff --name-only HEAD~1 HEAD'
g config --global commit.gpgsign true
g config --global alias.sign '!f() { git rebase --exec "git commit --amend --no-edit -S" HEAD~"$1"; }; f'
g config --global user.signingkey GPG_KEY_ID
```

```shell
echo "file" >> .git/info/exclude
```

## Appendix
```shell
git branch -m master main
git fetch origin
git branch -u origin/main main
git remote set-head origin -a
```