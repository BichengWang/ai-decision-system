
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
make bootstrap
make env
source venv/bin/activate
python -m pip install -U pip-tools
pip-compile requirements.in
pip install -r requirements.txt
```
#### Refresh Dependencies
```
pip install pip-tools>=4.2.0
pip-compile --no-emit-index-url requirements.in
```
or add current environment full requirements into file
```
pip freeze > requirements.txt
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
