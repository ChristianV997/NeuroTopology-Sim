from shared.data_loaders.eeg_bids_loader import EEGMetadata,validate_band_nyquist

def test_nyquist_guard():
 validate_band_nyquist(EEGMetadata(5000,(),None,"local","x"),100)
 try: validate_band_nyquist(EEGMetadata(100,(),None,"local","x"),80)
 except ValueError: pass
 else: raise AssertionError("Nyquist violation accepted")
