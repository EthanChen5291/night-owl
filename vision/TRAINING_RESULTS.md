# Detector training results

The target in this experiment is a dark plush rat moved through lit room scenes recorded by the Barn Owl camera. Codex agents visually reviewed frames and drew boxes around the visible plush body. The labels have no independent human signoff. Infrared recordings were inspected but excluded because object identity was too uncertain to label reliably. These results do not measure detection of live rats or dark-room performance.

| Run | Physical training clips | Whole held-out clips | Train frames / rat / person / empty | Validation frames / rat / person / empty | Dataset SHA-256 | Result |
| --- | --- | --- | --- | --- | --- | --- |
| v1 | `table_a`, `zoom2_a` | `zoom15_b` | 54 / 32 / 0 / 22 | 22 / 17 / 0 / 5 | `428d0afe22e75081283aca3310992de9f6c1bbe75a616a3f1eb4b3bde4e0b407` | Failed: PyTorch rat AP50 0.00755; ONNX rat AP50 0.01176. |
| v2 | `table_a`, `table_b`, `zoom2_a`, `zoom15_a` | `zoom15_b`, `table_c` | 252 / 122 / 20 / 114 | 49 / 29 / 12 / 12 | `52d386b7d67e930e8929f62464664220723beac888f90b982934c3be7a063d04` | Failed: matched square-416 rat AP50 0.79031 for both PyTorch and ONNX. |

Each dataset is grayscale replicated across three channels to match Pi inference. Frame lists and split tags are in the corresponding `dataset/manifest.json` snapshots. The v2 dataset fingerprint in the training report hashes every image/label path and file hash. A full-directory hash, including `data.yaml` and the manifest, is `eea677dc8e35aca3e3fcfdc4c26c67e9f024de6d2ca5d3ccec09a38ce425092a`; the v2 manifest SHA-256 is `ae62db7c06a99e289fa878ab1b6d9804da320b42dd8c4cd1ea2cb1759cbf764c`. The saved v2 snapshot has the same manifest hash as the source dataset. V2's `*_dense` tags contain additional 0.5 fps samples from the four physical training clips; they are not independent recordings. Both v2 validation recordings are absent from training. All included frames have a review marker and a label file; empty files mean no labeled target or person.

V1 ran on a bounded NVIDIA L4 job from pretrained `yolo11n.pt` at 416 pixels, batch 16. It stopped early after 27 of 60 requested epochs, with only four batches per epoch. Raw PyTorch-to-ONNX parity passed on five validation images, but rat AP50 was far below the 0.9 gate and the person class had no training labels. Its candidate was retained for analysis and was not promoted to the Pi. V2 added varied lit positive and negative frames and 20 reviewed person boxes. It ran all 150 requested epochs on a bounded L4 job with batch 8 and a reduced augmentation recipe. Under matched square-416 validation (`rect=False`, batch 1, confidence 0.001, IoU 0.7), PyTorch and ONNX had identical AP50: rat 0.79031 and person 0.84326. Raw tensor parity on five inputs also passed. The initial report compared default rectangular PyTorch validation (rat 0.84353) with square ONNX validation (rat 0.79000); its apparent 0.05353 gap was a validation geometry mismatch, not evidence of a conversion error. Deployment-shape rat AP50 still missed the 0.9 gate, so no v2 candidate was promoted to the Pi.

| V2 held-out clip | Frames | Rat boxes | PyTorch rat AP50 | ONNX rat AP50 |
| --- | ---: | ---: | ---: | ---: |
| `zoom15_b` | 22 | 17 | 0.93674 | 0.93674 |
| `table_c` | 27 | 12 | 0.65108 | 0.65108 |

The per-clip scores use the same square-416 settings for PyTorch and ONNX. The strong close-zoom score conceals weaker generalization on `table_c`. Event-level validation has not run because reviewed push timestamps and a negative reel are still needed. These results do not support the intended unattended alerting behavior.

The v1 and v2 reports are retained locally under `runs/modal-rat-20260926/` and `runs/modal-rat-v2-20260926/`. The ignored source clips, contact sheets, review markers, and v2 dataset remain local to the working checkout. This tracked note contains no footage, credentials, or recording IDs.
