"""Concordance — lemma index + KWIC queries.

Built on the ``chunk_lemmas`` cache + the ``chunks_full`` view; mirrors
``reader.queries`` in shape so the HTTP handler layer stays uniform.
"""
