"""Fetch pinned official PDF originals only; no model calls."""
from run_native_pdf_v5 import get_pdf,sources
if __name__=='__main__':
    for ident,source in sources().items():
        raw=get_pdf(source);print(ident,len(raw),'bytes verified')
