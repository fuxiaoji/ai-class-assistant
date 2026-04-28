import av
print('PyAV version:', av.__version__)
print('WebM demux support:', 'webm' in av.formats_available)
print('WAV mux support:', 'wav' in av.formats_available)
print('matroska demux support:', 'matroska' in av.formats_available)
