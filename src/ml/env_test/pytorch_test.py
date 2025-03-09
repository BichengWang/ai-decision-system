import torch
import logging
import os

device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.mps.is_available() else 'cpu'


def env_test_gpu():
    if device == 'cuda':
        logging.info("CUDA is available. GPU is working.")
        logging.info("GPU Name: %s", torch.cuda.get_device_name(0))
        logging.info('__CUDNN VERSION: %s', torch.backends.cudnn.version())
        logging.warning('cuda version: {}'.format(torch.version.cuda))
        logging.warning('CUDA_PATH: {}'.format(os.environ["CUDA_PATH"]))
        logging.warning('CUDA_HOME: {}'.format(os.environ["CUDA_HOME"]))
        logging.info('__Number CUDA Devices: %d', torch.cuda.device_count())
        logging.info('__CUDA Device Name: %s', torch.cuda.get_device_name(0))
        logging.info('__CUDA Device Total Memory [GB]: %.2f',
                     torch.cuda.get_device_properties(0).total_memory / 1e9)
    elif device == 'mps':
        logging.info("MPS is available. MPS is working.")
        logging.info("GPU Name: %s", torch.mps.get_device_name(0))
        logging.info('__Number Devices: %d', torch.mps.device_count())
        logging.info('Device Name: %s', torch.mps.get_device_name(0))
        logging.info('Device Total Memory [GB]: %.2f',
                     torch.mps.get_device_properties(0).total_memory / 1e9)
    else:
        logging.info("CUDA is not available. CPU is working.")
    return


def stress_test_gpu(iterations=500, tensor_size=(128, 128), device=device):
    for i in range(1, iterations+1):
        if i % 100 == 0:
            logging.info(f"Iteration: {i}")
        x = torch.rand(tensor_size, device=device)
        y = torch.rand(tensor_size, device=device)
        z = x * y
        del x, y, z


def torch_vision_test():
    # fix env: conda install -c anaconda pillow
    import torchvision

    x = torch.randn(32, 32, device=device)
    model = torchvision.models.resnet18().to(device)

    logging.info(x.device)
    logging.info(next(model.parameters()).device)


def transformers_test():
    from transformers import BertModel, BertTokenizer
    
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
    model = BertModel.from_pretrained('bert-base-uncased').to(device)

    _ = tokenizer("Hello, my dog is cute", return_tensors="pt").to(device)

    logging.info("Transformers model and tokenizer are available and working.")
    logging.info(f"Model device: {next(model.parameters()).device}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    env_test_gpu()
    stress_test_gpu()
    torch_vision_test()
    transformers_test()
    logging.info("All tests passed.")
