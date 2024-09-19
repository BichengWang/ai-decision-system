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

## Conda

```shell
brew install --cask anaconda
```

### Create Conda Env

```shell
conda remove -n python-notebook --all
conda create --name python-notebook python=3.9
conda info --envs
activate python-notebook
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
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.st status
git config --global alias.ll "log --oneline"
git config --global alias.lg "log --oneline --graph --all --decorate"
git config --global alias.rb "pull --rebase origin"
git config --global alias.sq "rebase -i HEAD~10"
git config --global alias.dl '!git branch -D $1 && git push --delete origin $1'
git config --global push.default current
git config --global core.editor "vim"
```

Pull and rebase origin master

```shell
git pull --rebase origin master
```

## Appendix

To test which python in path

```shell
import sys
print(sys.path)
```

tensorflow & pytorch for M1
https://caffeinedev.medium.com/how-to-install-tensorflow-on-m1-mac-8e9b91d93706
https://pytorch.org/get-started/locally/
https://developer.apple.com/forums/thread/695963

For test
