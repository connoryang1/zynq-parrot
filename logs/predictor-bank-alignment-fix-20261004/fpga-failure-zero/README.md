# Exact-placement zero-value diagnostic

This companion retains the same exact loop addresses and byte-identical loop
bodies. Its bits report: bit 0, returning context is nonzero; bit 1, peer
completion is zero; bit 2, peer terminal context is zero.

Both corrected bitstream `7994ad2f...` and previous qualified bitstream
`9704dd6e...` report code 6 for a one-request warmup. Thus both peer records
remain literally zero while context zero returns. Because the behavior exists
on both images, it is a separate short-stream lifecycle edge case rather than
a regression from the predictor-bank correction.
