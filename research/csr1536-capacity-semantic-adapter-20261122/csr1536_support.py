"""Pure assertion shared by byte-identical semantic methods."""
def require(value,message):
    if not value:raise ValueError(message)
