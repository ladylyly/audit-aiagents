//! BP⁺ 4 × 64-bit range proof that hides a full 256-bit Ethereum tx-hash.

use curve25519_dalek::{
    ristretto::CompressedRistretto,
    scalar::Scalar,
};
use merlin::Transcript;
use rand::rngs::OsRng;
use rand::{RngCore, CryptoRng};
use tari_bulletproofs_plus::{
    commitment_opening::CommitmentOpening,
    generators::pedersen_gens::ExtensionDegree,
    range_parameters::RangeParameters,
    range_proof::VerifyAction,
    range_statement::RangeStatement,
    range_witness::RangeWitness,
    ristretto::{create_pedersen_gens_with_extension_degree, RistrettoRangeProof},
};

const LABEL: &[u8]   = b"TxID-BP+-256bit";
const LIMB_BITS: usize = 64;            // each limb ∈ [0, 2⁶⁴)
const LIMBS: usize     = 4;             // 4 × 64 = 256 bits

/// Produce a BP⁺ proof for a full 32-byte tx-hash.
/// Returns `(commitments, proof bytes)`.
pub fn prove_txid_commitment(hash: [u8; 32]) -> (Vec<CompressedRistretto>, Vec<u8>) {
    let mut rng = OsRng;
    prove_txid_commitment_with_rng(hash, &mut rng)
}

/// Produce a BP⁺ proof for a full 32-byte tx-hash with a provided RNG.
/// This version allows using a faster RNG (like ThreadRng) for testing/benchmarking.
/// Returns `(commitments, proof bytes)`.
pub fn prove_txid_commitment_with_rng<R: RngCore + CryptoRng>(
    hash: [u8; 32],
    rng: &mut R,
) -> (Vec<CompressedRistretto>, Vec<u8>) {
    // 1️⃣ split hash into four little-endian 64-bit limbs
    let limbs: [u64; LIMBS] = [
        u64::from_le_bytes(hash[0..8].try_into().unwrap()),
        u64::from_le_bytes(hash[8..16].try_into().unwrap()),
        u64::from_le_bytes(hash[16..24].try_into().unwrap()),
        u64::from_le_bytes(hash[24..32].try_into().unwrap()),
    ];

    // 2️⃣ generators & parameters
    // Note: These are created each time (same as BP's approach for consistency)
    // In production, they could be cached, but for benchmarking we match BP's behavior
    let pc_gens = create_pedersen_gens_with_extension_degree(ExtensionDegree::DefaultPedersen);
    let params  = RangeParameters::init(LIMB_BITS, LIMBS, pc_gens.clone()).unwrap();

    // 3️⃣ commit each limb
    let mut commitments = Vec::with_capacity(LIMBS);
    let mut openings    = Vec::with_capacity(LIMBS);
    for &limb in &limbs {
        let blind = Scalar::random(rng);
        let com = pc_gens.commit(&Scalar::from(limb), &[blind]).unwrap();
        commitments.push(com.compress());
        openings.push(CommitmentOpening::new(limb, vec![blind]));
    }

    // 4️⃣ witness & statement
    let witness   = RangeWitness::init(openings).unwrap();
    let statement = RangeStatement::init(
        params,
        commitments.iter().map(|c| c.decompress().unwrap()).collect(),
        vec![None; LIMBS],
        None
    ).unwrap();

    // 5️⃣ prove
    // Note: BP+ requires RNG during proof generation (unlike BP which uses pre-computed blinding)
    // This is a fundamental difference in the APIs
    let mut transcript = Transcript::new(LABEL);
    let proof = RistrettoRangeProof::prove_with_rng(&mut transcript, &statement, &witness, rng).unwrap();

    (commitments, proof.to_bytes())
}

/// Verify a BP⁺ proof produced above.
pub fn verify_txid_commitment(
    commitments: Vec<CompressedRistretto>,
    proof_bytes: Vec<u8>,
) -> bool {
    if commitments.len() != LIMBS {
        return false;
    }
    // deserialize proof
    let proof = match RistrettoRangeProof::from_bytes(&proof_bytes) {
        Ok(p) => p,
        Err(_) => return false,
    };

    // params
    let pc_gens = create_pedersen_gens_with_extension_degree(ExtensionDegree::DefaultPedersen);
    let params  = RangeParameters::init(LIMB_BITS, LIMBS, pc_gens).unwrap();

    // decompress commitments; bail if malformed
    let decompressed: Option<Vec<_>> = commitments.iter().map(|c| c.decompress()).collect();
    let decompressed = match decompressed {
        Some(v) => v,
        None => return false,
    };

    let statement = RangeStatement::init(
        params,
        decompressed,
        vec![None; LIMBS],
        None
    ).unwrap();

    let transcript = Transcript::new(LABEL);
    RistrettoRangeProof::verify_batch(
        &mut vec![transcript],
        &vec![statement],
        &vec![proof],
        VerifyAction::VerifyOnly,
    )
    .is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::RngCore;

    #[test]
    fn valid_bp_plus_roundtrip() {
        let mut hash = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut hash);
        let (coms, p) = prove_txid_commitment(hash);
        assert!(verify_txid_commitment(coms, p));
    }

    #[test]
    fn invalid_bp_plus_proof() {
        let hash = [1u8; 32];
        let (coms, mut p) = prove_txid_commitment(hash);
        p[5] ^= 0xAB; // corrupt proof
        assert!(!verify_txid_commitment(coms, p));
    }
}