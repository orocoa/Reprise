"""A nonvisual project: Git history is usable even without a browser runtime."""
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('name', nargs='?', default='Reprise')
args = parser.parse_args()
print('Hello, ' + args.name)
