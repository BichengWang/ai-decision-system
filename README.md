# python-notebook
## Motto
Being Honest with Yourself.
## Auth
bichengwang17@gmail.com
## Recommend Env
The recommended running env is conda env to avoid some windows crash or compile issue.
## Directory Structure
In different directory, it would content specific readme file for different code tools.
## Makefile
```
python -m pip install --upgrade pip
make env
source venv/bin/activate
make bootstrap
python -m pip install -U pip-tools
pip install -r requirements.txt
```
#### Refresh Dependencies
```
pip install pip-tools>=4.2.0
pip-compile --no-emit-index-url requirements.in
```
Optional: add current environment full requirements into file
```
pip freeze > requirements.txt
```
Checking: check specific lib exist or not
```
pip freeze | grep tensorflow-gpu
```
## Conda
```
conda create --name python-notebook python=3.7
conda info --envs
```

```
activate python-notebook
```
install libs
```angular2html
conda install pywin32
```
## Git
pruning origin deleted branches
```
git remote prune origin
```

git global config for all general commands:
```
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.st status
git config --global alias.ll "log --oneline"
```
