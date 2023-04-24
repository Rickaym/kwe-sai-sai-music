import importlib

from os import listdir

class Path:
    LAYER1 = 'bot'
    LAYER2 = ['exts', 'assets', 'utils']
    LAYER3 = ['admin']

def get_extensions():
    """
    Loops through directories and subdirectories to find for cogs that can be
    load into
    """
    base = f'./{Path.LAYER1}/{Path.LAYER2[0]}/'
    path = ''
    for subdirectory in listdir(base):
        path += f'{Path.LAYER1}.{Path.LAYER2[0]}.{subdirectory}.'

        for file in listdir(base+subdirectory):
            if file.startswith("_"):
                continue
            if file.endswith("py"):
                if not file.startswith("IO"):
                    mod = importlib.import_module(path+file[:-3])
                    # Target module doesn't have a setup function--is not a cog
                    if getattr(mod, "setup", None) is None:
                        continue
                path += str(file)[:-3]
                yield path
            path = '.'.join(path.split('.')[:-1]) + '.'
        path = ''

EXTENSIONS = frozenset(get_extensions())