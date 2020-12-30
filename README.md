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
