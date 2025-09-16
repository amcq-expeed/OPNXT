import argparse
from .service import hello

def main():
    parser = argparse.ArgumentParser(description='Generated app CLI')
    parser.add_argument('--name', default='World')
    args = parser.parse_args()
    print(hello(args.name))

if __name__ == '__main__':
    main()
