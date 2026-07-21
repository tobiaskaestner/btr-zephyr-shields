"""rigexp — expander prototype (architecture.md terms).

Components:
  loaders (loader_dts / loader_yml)  text -> rig model   (language errors)
  model                              the rig model        (declared facts only)
  analyzer                           rig model -> solved rig (physics errors)
  emitter                            solved rig -> overlay + config sheet
                                     + expectations (pure rendering, no errors)
"""
