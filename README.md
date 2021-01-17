# python-notebook
### Auth
### Makefile
```
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
```

