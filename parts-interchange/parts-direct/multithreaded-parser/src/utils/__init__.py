
def format_print_msg(message, level = 0):
    print('    ' * level + message)

def get_file_name(url: str):
    return url.split('/')[-1]
