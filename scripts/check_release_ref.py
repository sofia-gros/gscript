"""Do not publish artifacts if their tested release tag has moved or disappeared."""
import subprocess
import sys


def main():
    tag='refs/tags/'+sys.argv[1]
    expected=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    refs=subprocess.check_output(['git','ls-remote','origin',tag,tag+'^{}'],text=True)
    remote=dict(reversed(line.split()) for line in refs.splitlines())
    actual=remote.get(tag+'^{}',remote.get(tag))
    if actual!=expected:
        raise SystemExit('release tag no longer points to the tested commit; publication stopped')
    print('Release tag and tested artifact commit verified')


if __name__=='__main__':main()
