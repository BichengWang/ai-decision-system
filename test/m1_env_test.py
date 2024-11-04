import time
import numpy as np
import sys
import os



if __name__ == "__main__":
    # check path
    print(sys.path)
    
    # check environment
    os.system('nvcc --version')
    os.system('nvidia-smi')
    os.system('python --version')
    
    
    
    np.random.seed(42)
    a = np.random.uniform(size=(300, 300))
    runtimes = 10

    timecosts = []
    for _ in range(runtimes):
        s_time = time.time()
        for i in range(100):
            a += 1
            np.linalg.svd(a)
        timecosts.append(time.time() - s_time)

    print(f'mean of {runtimes} runs: {np.mean(timecosts):.5f}s')
