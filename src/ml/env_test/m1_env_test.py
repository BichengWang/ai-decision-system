import logging
import sys
import os
import pytorch_test as torch_test


def try_test(func):
    try:
        func()
    except Exception as e:
        logging.error(e)
    return


if __name__ == "__main__":
    # check path
    print(sys.path)
    
    # check environment
    os.system('nvcc --version')
    os.system('nvidia-smi')
    os.system('python --version')
    
    for name in dir(torch_test):
        if callable(getattr(torch_test, name)):
            try_test(getattr(torch_test, name))
