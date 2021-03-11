# python-notebook
### Auth
@bichengwang17@gmail.com
### Recommend Env
The recommended running env is conda env to avoid some windows crash or compile issue.
### Makefile
```
python -m pip install --upgrade pip
pip-compile requirements.in
make bootstrap
make env
source venv/bin/activate
```
#### Refresh Dependencies
```
pip install pip-tools>=4.2.0
pip-compile --no-emit-index-url requirements.in
```
### Git
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
git config --global alias.ll "log --online"
```

