import torch
import logging


device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.mps.is_available() else 'cpu'


def env_test_gpu():
    if device == 'cuda':
        logging.info("CUDA is available. GPU is working.")
        logging.info("GPU Name:", torch.cuda.get_device_name(0))
        logging.info('__CUDNN VERSION:', torch.backends.cudnn.version())
        logging.info('__Number CUDA Devices:', torch.cuda.device_count())
        logging.info('__CUDA Device Name:',torch.cuda.get_device_name(0))
        logging.info('__CUDA Device Total Memory [GB]:',torch.cuda.get_device_properties(0).total_memory/1e9)
    elif device == 'mps':
        logging.info("MPS is available. MPS is working.")
        logging.info("GPU Name:", torch.mps.get_device_name(0))
        logging.info('__Number CUDA Devices:', torch.mps.device_count())
        logging.info('__CUDA Device Name:',torch.mps.get_device_name(0))
        logging.info('__CUDA Device Total Memory [GB]:',torch.mps.get_device_properties(0).total_memory/1e9)
    else:
        logging.info("CUDA is not available. CPU is working.")
    return


def stress_test_gpu(iterations=1000, tensor_size=(1024, 1024), device=device):
    for i in range(iterations):
        if i % 100 == 0:
            logging.info(f"Iteration: {i}")
        x = torch.rand(tensor_size, device=device)
        y = torch.rand(tensor_size, device=device)
        z = x * y
        del x, y, z


def torch_vision_test():
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
