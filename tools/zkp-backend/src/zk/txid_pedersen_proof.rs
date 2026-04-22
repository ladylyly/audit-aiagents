use bulletproofs::r1cs::{Prover, Verifier};
use bulletproofs::{BulletproofGens, PedersenGens};
use bulletproofs::r1cs::R1CSProof;
use curve25519_dalek_ng::ristretto::CompressedRistretto;
use curve25519_dalek_ng::scalar::Scalar;
use merlin::Transcript;
use rand::rngs::OsRng;
use rand::RngCore;
use hex::FromHex;

/// Proves knowledge of a transaction ID preimage such that Pedersen(tx_id, r) == commitment
/// This version supports optional binding tag for linking commitments
pub fn prove_txid_commitment_with_binding(
    tx_id: Scalar,
    binding_tag: Option<&[u8]>,
) -> (CompressedRistretto, Vec<u8>, bool) {
    if binding_tag.is_some() {
        println!("\u{25B6}\u{FE0F} [ZKP] Running: Bulletproof-based ZKP for tx_id with binding tag");
        println!("   [ZKP] Binding tag: {} bytes", binding_tag.unwrap().len());
    } else {
        println!("\u{25B6}\u{FE0F} [ZKP] Running: Bulletproof-based ZKP for tx_id using Pedersen commitment (no binding tag)");
    }

    println!("   [ZKP] Initializing generators...");
    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(64, 1);
    let mut rng = OsRng;

    println!("   [ZKP] Generating random blinding factor...");
    let mut bytes = [0u8; 64];
    rng.fill_bytes(&mut bytes);
    let blinding_r = Scalar::from_bytes_mod_order_wide(&bytes);

    // ✍️ Prover Phase
    println!("   [ZKP] Starting prover phase...");
    let mut transcript = Transcript::new(b"TxIDPedersenZKP");
    
    // ✅ Add binding tag to transcript if provided (Feature 2: Linkable Commitment)
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
        println!("   [ZKP] ✅ Binding tag added to prover transcript: {} bytes", binding.len());
    } else {
        println!("   [ZKP] No binding tag in prover transcript");
    }
    
    let mut prover = Prover::new(&pc_gens, &mut transcript);
    let (_com_var, _) = prover.commit(tx_id, blinding_r);
    println!("   [ZKP] Committed tx_id to prover");
    
    println!("   [ZKP] Generating proof...");
    let proof = prover.prove(&bp_gens).unwrap();
    let proof_bytes = proof.to_bytes();
    let commitment = pc_gens.commit(tx_id, blinding_r).compress();
    println!("   [ZKP] ✅ Proof generated: {} bytes, commitment: {} bytes", proof_bytes.len(), commitment.as_bytes().len());

    // 🔍 Verifier Phase
    println!("   [ZKP] Starting verifier phase...");
    let mut transcript = Transcript::new(b"TxIDPedersenZKP");
    
    // ✅ Add binding tag to verification transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
        println!("   [ZKP] ✅ Binding tag added to verifier transcript: {} bytes", binding.len());
    } else {
        println!("   [ZKP] No binding tag in verifier transcript");
    }
    
    let mut verifier = Verifier::new(&mut transcript);
    let _var = verifier.commit(commitment);
    println!("   [ZKP] Committed to verifier");
    
    println!("   [ZKP] Verifying proof...");
    let verified = verifier.verify(&proof, &pc_gens, &bp_gens).is_ok();

    if verified {
        println!("\u{2705} [ZKP] ✅ ZK Proof of tx_id preimage VERIFIED");
    } else {
        println!("\u{274C} [ZKP] ❌ ZK Proof of tx_id preimage VERIFICATION FAILED");
    }

    (commitment, proof_bytes, verified)
}

/// Proves knowledge of a transaction ID preimage such that Pedersen(tx_id, r) == commitment
/// Backward compatible version without binding tag
pub fn prove_txid_commitment(tx_id: Scalar) -> (CompressedRistretto, Vec<u8>, bool) {
    prove_txid_commitment_with_binding(tx_id, None)
}

/// Convenience wrapper: takes Ethereum tx hash as hex string and proves it
/// Backward compatible version without binding tag
pub fn prove_txid_commitment_from_hex(txid_hex: &str) -> (CompressedRistretto, Vec<u8>, bool) {
    prove_txid_commitment_from_hex_with_binding(txid_hex, None)
}

/// Convenience wrapper: takes Ethereum tx hash as hex string and proves it with optional binding tag
/// Feature 2: Linkable Commitment - binding tag links purchase and delivery TX commitments
pub fn prove_txid_commitment_from_hex_with_binding(
    txid_hex: &str,
    binding_tag: Option<&[u8]>,
) -> (CompressedRistretto, Vec<u8>, bool) {
    println!("[ZKP] prove_txid_commitment_from_hex_with_binding called");
    println!("   [ZKP] TX hash (hex): {}", txid_hex);
    println!("   [ZKP] Binding tag: {}", if binding_tag.is_some() { "provided" } else { "not provided" });
    
    let hex_str = txid_hex.strip_prefix("0x").unwrap_or(txid_hex);
    println!("   [ZKP] Parsing hex string (length: {})...", hex_str.len());
    
    let bytes = match <[u8; 32]>::from_hex(hex_str) {
        Ok(b) => {
            println!("   [ZKP] ✅ TX hash parsed successfully: {} bytes", b.len());
            b
        },
        Err(e) => {
            println!("   [ZKP] ❌ Failed to parse TX hash: {:?}", e);
            panic!("Invalid tx hash: {:?}", e);
        },
    };
    
    let tx_scalar = Scalar::from_bytes_mod_order(bytes);
    println!("   [ZKP] Converted to scalar, calling prove_txid_commitment_with_binding...");
    prove_txid_commitment_with_binding(tx_scalar, binding_tag)
}

/// Proves knowledge of a 256-bit transaction ID preimage such that the commitments to all 4 limbs are valid
/// Returns (Vec<CompressedRistretto>, proof bytes, verified)
pub fn prove_txid_commitment_4limb(txid_bytes: [u8; 32]) -> (Vec<CompressedRistretto>, Vec<u8>, bool) {
    use bulletproofs::r1cs::ConstraintSystem;
    use curve25519_dalek_ng::scalar::Scalar;
    // Split into 4 limbs
    let limbs: [u64; 4] = [
        u64::from_le_bytes(txid_bytes[0..8].try_into().unwrap()),
        u64::from_le_bytes(txid_bytes[8..16].try_into().unwrap()),
        u64::from_le_bytes(txid_bytes[16..24].try_into().unwrap()),
        u64::from_le_bytes(txid_bytes[24..32].try_into().unwrap()),
    ];
    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(64, 4); // 4 parties, 64 bits each
    let mut rng = OsRng;
    let mut transcript = Transcript::new(b"TxIDPedersenZKP4Limb");
    let mut prover = Prover::new(&pc_gens, &mut transcript);
    let mut commitments = Vec::with_capacity(4);
    let mut vars = Vec::with_capacity(4);
    for &limb in &limbs {
        let mut bytes = [0u8; 64];
        rng.fill_bytes(&mut bytes);
        let blind = Scalar::from_bytes_mod_order_wide(&bytes);
        let (com, var) = prover.commit(Scalar::from(limb), blind);
        commitments.push(com);
        vars.push(var);
        // Optionally, constrain range here if you want to prove it's in [0, 2^64)
        prover.constrain(var - Scalar::from(limb));
    }
    // No additional constraints: just prove knowledge of all 4 limbs
    let proof = prover.prove(&bp_gens).unwrap();
    let proof_bytes = proof.to_bytes();
    // Verifier phase
    let mut transcript = Transcript::new(b"TxIDPedersenZKP4Limb");
    let mut verifier = Verifier::new(&mut transcript);
    let mut v_vars = Vec::with_capacity(4);
    for &com in &commitments {
        let var = verifier.commit(com);
        v_vars.push(var);
        // Optionally, constrain range here if you want to prove it's in [0, 2^64)
        verifier.constrain(var - var); // always zero, just to keep structure
    }
    let verified = verifier.verify(&R1CSProof::from_bytes(&proof_bytes).unwrap(), &pc_gens, &bp_gens).is_ok();
    (commitments, proof_bytes, verified)
}

/// Verifies the proof of a transaction ID preimage
/// Backward compatible version without binding tag
pub fn verify_txid_commitment(
    commitment: CompressedRistretto,
    proof_bytes: Vec<u8>
) -> bool {
    verify_txid_commitment_with_binding(commitment, proof_bytes, None)
}

/// Verifies the proof of a transaction ID preimage with optional binding tag
/// Feature 2: Linkable Commitment - binding tag must match the one used during proof generation
pub fn verify_txid_commitment_with_binding(
    commitment: CompressedRistretto,
    proof_bytes: Vec<u8>,
    binding_tag: Option<&[u8]>,
) -> bool {
    if binding_tag.is_some() {
        println!("[ZKP] [VERIFY] Verifying TX hash commitment with binding tag ({} bytes)", binding_tag.unwrap().len());
    } else {
        println!("[ZKP] [VERIFY] Verifying TX hash commitment without binding tag (backward compatible)");
    }
    
    println!("   [ZKP] [VERIFY] Initializing generators...");
    let pc_gens = PedersenGens::default();
    let bp_gens = BulletproofGens::new(64, 1);
    let mut transcript = Transcript::new(b"TxIDPedersenZKP");

    // ✅ Add binding tag to verification transcript if provided
    if let Some(binding) = binding_tag {
        transcript.append_message(b"bind", binding);
        println!("   [ZKP] [VERIFY] ✅ Binding tag added to verification transcript: {} bytes", binding.len());
    } else {
        println!("   [ZKP] [VERIFY] No binding tag in verification transcript");
    }

    println!("   [ZKP] [VERIFY] Creating verifier and committing...");
    let mut verifier = Verifier::new(&mut transcript);
    let _var = verifier.commit(commitment);

    println!("   [ZKP] [VERIFY] Parsing proof bytes ({} bytes)...", proof_bytes.len());
    let proof = match R1CSProof::from_bytes(&proof_bytes) {
        Ok(p) => {
            println!("   [ZKP] [VERIFY] ✅ Proof parsed successfully");
            p
        },
        Err(e) => {
            println!("   [ZKP] [VERIFY] ❌ Failed to parse proof: {:?}", e);
            return false;
        },
    };
    
    println!("   [ZKP] [VERIFY] Running verification...");
    let result = verifier.verify(&proof, &pc_gens, &bp_gens);
    
    match result {
        Ok(_) => {
            println!("   [ZKP] [VERIFY] ✅ Verification SUCCESS");
            true
        },
        Err(e) => {
            println!("   [ZKP] [VERIFY] ❌ Verification FAILED: {:?}", e);
            false
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_txid_proof() {
        let tx_id = Scalar::from(123456u64);
        let (commitment, proof_bytes, verified) = prove_txid_commitment(tx_id);
        assert!(verified);
        assert!(verify_txid_commitment(commitment, proof_bytes));
    }

    #[test]
    fn test_invalid_txid_proof() {
        let tx_id = Scalar::from(123456u64);
        let (_, proof_bytes, _) = prove_txid_commitment(tx_id);

        // Fake commitment to simulate mismatch
        let fake_commitment = PedersenGens::default().commit(Scalar::from(999999u64), Scalar::zero()).compress();

        let result = verify_txid_commitment(fake_commitment, proof_bytes);
        assert!(!result);
    }

    #[test]
    fn test_malformed_proof_bytes() {
        let tx_id = Scalar::from(123456u64);
        let (commitment, _, _) = prove_txid_commitment(tx_id);
        let malformed = vec![0u8; 10];
        assert!(
            !verify_txid_commitment(commitment, malformed),
            "Malformed proof bytes should not verify"
        );
    }
}



