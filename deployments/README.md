# StudioNet release evidence

`studionet.json` records the submission-candidate address and deployment transaction, the exact source and ABI hashes, the isolated deployer address, and the successful full-flow StudioNet test run for the same source hash. `contracts/abi.json` contains the full local ABI; the release-proof test compares it with the deployed schema. The full-flow and release-proof deployments are separate addresses, but are bound to identical source bytes. No key, mnemonic, keystore, password, or environment secret belongs in this directory.
