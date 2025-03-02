import requests


def get():
    url = 'https://w3schools.com/python/demopage.htm'
    x = requests.get(url)
    print(x.json())


def post():
    url = 'https://www.w3schools.com/python/demopage.php'
    myobj = {'somekey': 'somevalue'}
    x = requests.post(url, data=myobj)
    print(x.json())

def val(input, padding, filter, stride):
    return ((input + 2 * padding - filter) / stride) + 1

if __name__ == '__main__':
    # get()
    # post()
    print(val(128, 0, 3, 1))
    print(val(128, 2, 5, 1))
    print(val(128, 0, 2, 2))
