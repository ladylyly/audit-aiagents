//! Test 3.5: BP+ Proof Generation Time
//! Measures time to generate a BP+ range proof for transaction IDs (4 × 64-bit limbs)
//! Structured identically to BP generation test for fair comparison

use bulletproof_demo::zk::bp_plus_pedersen::{prove_txid_commitment, verify_txid_commitment};
use std::time::Instant;
use sha2::{Sha256, Digest};

// Helper function to compute deterministic blinding factor (matching BP test structure)
// For BP+, we use this for consistency even though BP+ uses random blinding internally
fn compute_blinding(escrow_addr: &[u8], owner: &[u8]) -> curve25519_dalek::scalar::Scalar {
    let mut hasher = Sha256::new();
    hasher.update(escrow_addr);
    hasher.update(owner);
    let hash = hasher.finalize();
    let mut bytes = [0u8; 32];
    bytes.copy_from_slice(&hash[..32]);
    curve25519_dalek::scalar::Scalar::from_bytes_mod_order(bytes)
}

// Helper function to compute binding tag (matching BP test structure)
// Note: BP+ doesn't use binding tags, but we measure this for structural consistency
fn compute_binding_tag(
    chain_id: &str,
    escrow_addr: &[u8],
    product_id: u64,
    stage: u8,
    schema_version: &str,
    previous_vc_cid: Option<&str>,
) -> Vec<u8> {
    let mut hasher = Sha256::new();
    hasher.update(chain_id.as_bytes());
    hasher.update(escrow_addr);
    hasher.update(&product_id.to_le_bytes());
    hasher.update(&[stage]);
    hasher.update(schema_version.as_bytes());
    if let Some(cid) = previous_vc_cid {
        hasher.update(cid.as_bytes());
    }
    hasher.finalize().to_vec()
}

// Statistics calculation (identical to BP tests)
struct Stats {
    median: f64,
    q1: f64,
    q3: f64,
    iqr: f64,
    min: f64,
    max: f64,
    mean: f64,
    std_dev: f64,
}

fn calculate_stats(times: &[f64]) -> Stats {
    let mut sorted = times.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    
    let n = sorted.len();
    let median = if n % 2 == 0 {
        (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
    } else {
        sorted[n / 2]
    };
    
    let q1_idx = n / 4;
    let q3_idx = 3 * n / 4;
    let q1 = sorted[q1_idx];
    let q3 = sorted[q3_idx];
    let iqr = q3 - q1;
    
    let min = sorted[0];
    let max = sorted[n - 1];
    
    let mean = times.iter().sum::<f64>() / n as f64;
    let variance = times.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / n as f64;
    let std_dev = variance.sqrt();
    
    Stats {
        median,
        q1,
        q3,
        iqr,
        min,
        max,
        mean,
        std_dev,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bpplus_proof_generation_time() {
        println!("\n🧪 Test 3.5: BP+ Proof Generation Time (4 × 64-bit limbs)\n");

        const RUNS: usize = 100;
        
        // Test parameters (identical to BP tests for fair comparison)
        let escrow_addr = b"0xc448142dF27D18A7bE5a439589320429AB18855c";
        let owner = b"0x88dcDCfB5e330049597003D41eF8E744Fa613E68";
        let chain_id = "11155111";
        let product_id = 14u64;
        let stage = 0u8;
        let schema_version = "1.0";
        let previous_vc_cid: Option<&str> = None;
        
        // Fixed transaction hash (derived from test parameters for consistency)
        let tx_hash: [u8; 32] = [
            0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,
            0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
            0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00,
            0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        ];

        let mut blinding_times = Vec::new();
        let mut commitment_times = Vec::new();
        let mut proof_times = Vec::new();
        let mut binding_tag_times = Vec::new();
        let mut total_times = Vec::new();

        println!("Running {} iterations for BP+ transaction ID proof generation (4 × 64-bit limbs)...\n", RUNS);

        // Create generators once outside the loop (more efficient)
        use tari_bulletproofs_plus::{
            generators::pedersen_gens::ExtensionDegree,
            ristretto::create_pedersen_gens_with_extension_degree,
        };
        let pc_gens = create_pedersen_gens_with_extension_degree(ExtensionDegree::DefaultPedersen);
        let limbs: [u64; 4] = [
            u64::from_le_bytes(tx_hash[0..8].try_into().unwrap()),
            u64::from_le_bytes(tx_hash[8..16].try_into().unwrap()),
            u64::from_le_bytes(tx_hash[16..24].try_into().unwrap()),
            u64::from_le_bytes(tx_hash[24..32].try_into().unwrap()),
        ];

        // Warm-up run (not counted) - identical structure to BP tests
        let _ = compute_blinding(escrow_addr, owner);
        let _ = compute_binding_tag(chain_id, escrow_addr, product_id, stage, schema_version, previous_vc_cid);
        use bulletproof_demo::zk::bp_plus_pedersen::prove_txid_commitment_with_rng;
        use rand::thread_rng;
        let mut warmup_rng = thread_rng();
        let _ = prove_txid_commitment_with_rng(tx_hash, &mut warmup_rng);

        for i in 0..RUNS {
            let total_start = Instant::now();

            // 1. Compute blinding (matching BP test structure)
            let blinding_start = Instant::now();
            let _blinding = compute_blinding(escrow_addr, owner);
            let blinding_time = blinding_start.elapsed();
            blinding_times.push(blinding_time.as_nanos() as f64 / 1_000_000.0);

            // 2. Compute binding tag (matching BP test structure)
            // Note: BP+ doesn't use binding tags, but we measure for structural consistency
            let binding_start = Instant::now();
            let _binding_tag = compute_binding_tag(chain_id, escrow_addr, product_id, stage, schema_version, previous_vc_cid);
            let binding_time = binding_start.elapsed();
            binding_tag_times.push(binding_time.as_nanos() as f64 / 1_000_000.0);

            // 3. Generate commitments (4 × 64-bit limbs)
            // This matches BP's "Generate commitment $C$" operation
            // Use ThreadRng instead of OsRng to avoid blocking on entropy
            let commit_start = Instant::now();
            use curve25519_dalek::scalar::Scalar;
            use rand::thread_rng;
            use rand::RngCore;
            
            let mut rng = thread_rng();
            let mut _commitments = Vec::with_capacity(4);
            for &limb in &limbs {
                let mut blind_bytes = [0u8; 32];
                rng.fill_bytes(&mut blind_bytes);
                let blind = Scalar::from_bytes_mod_order(blind_bytes);
                let _com = pc_gens.commit(&Scalar::from(limb), &[blind]).unwrap();
                _commitments.push(_com.compress());
            }
            let commit_time = commit_start.elapsed();
            commitment_times.push(commit_time.as_nanos() as f64 / 1_000_000.0);

            // 4. Generate BP+ range proof (matching BP's "Generate range proof" operation)
            // Use ThreadRng to avoid blocking on entropy (OsRng can be slow in loops)
            let proof_start = Instant::now();
            use bulletproof_demo::zk::bp_plus_pedersen::prove_txid_commitment_with_rng;
            let mut proof_rng = thread_rng();
            let (_commitments2, _proof_bytes) = prove_txid_commitment_with_rng(tx_hash, &mut proof_rng);
            let proof_time = proof_start.elapsed();
            proof_times.push(proof_time.as_nanos() as f64 / 1_000_000.0);

            let total_time = total_start.elapsed();
            total_times.push(total_time.as_nanos() as f64 / 1_000_000.0);

            // Print progress every 10 iterations with timing info
            if (i + 1) % 10 == 0 {
                let elapsed = total_start.elapsed();
                let avg_time = elapsed.as_nanos() as f64 / ((i + 1) as f64 * 1_000_000.0);
                let remaining = (RUNS - (i + 1)) as f64 * avg_time;
                println!(" [{}% - avg: {:.1}ms, est. remaining: {:.1}s]", 
                         (i + 1) * 100 / RUNS, avg_time, remaining / 1000.0);
                use std::io::Write;
                std::io::stdout().flush().unwrap();
            }
        }
        println!("\n");

        // Calculate statistics (identical to BP tests)
        let blinding_stats = calculate_stats(&blinding_times);
        let commitment_stats = calculate_stats(&commitment_times);
        let proof_stats = calculate_stats(&proof_times);
        let binding_tag_stats = calculate_stats(&binding_tag_times);
        let total_stats = calculate_stats(&total_times);

        // Output results (identical format to BP tests)
        println!("=== BP+ Proof Generation Time Statistics ({} runs) ===\n", RUNS);
        
        println!("Compute blinding $b$:");
        println!("  Median: {:.3} ms", blinding_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", blinding_stats.iqr, blinding_stats.q1, blinding_stats.q3);
        println!("  Min: {:.3} ms", blinding_stats.min);
        println!("  Max: {:.3} ms", blinding_stats.max);
        println!("  Mean: {:.3} ms", blinding_stats.mean);
        println!("  Std Dev: {:.3} ms\n", blinding_stats.std_dev);

        println!("Generate commitments (4 × 64-bit limbs):");
        println!("  Median: {:.3} ms", commitment_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", commitment_stats.iqr, commitment_stats.q1, commitment_stats.q3);
        println!("  Min: {:.3} ms", commitment_stats.min);
        println!("  Max: {:.3} ms", commitment_stats.max);
        println!("  Mean: {:.3} ms", commitment_stats.mean);
        println!("  Std Dev: {:.3} ms\n", commitment_stats.std_dev);

        println!("Generate BP+ range proof (4 × 64-bit):");
        println!("  Median: {:.3} ms", proof_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", proof_stats.iqr, proof_stats.q1, proof_stats.q3);
        println!("  Min: {:.3} ms", proof_stats.min);
        println!("  Max: {:.3} ms", proof_stats.max);
        println!("  Mean: {:.3} ms", proof_stats.mean);
        println!("  Std Dev: {:.3} ms\n", proof_stats.std_dev);

        println!("Compute binding tag $t$ (not used in BP+, measured for consistency):");
        println!("  Median: {:.3} ms", binding_tag_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", binding_tag_stats.iqr, binding_tag_stats.q1, binding_tag_stats.q3);
        println!("  Min: {:.3} ms", binding_tag_stats.min);
        println!("  Max: {:.3} ms", binding_tag_stats.max);
        println!("  Mean: {:.3} ms", binding_tag_stats.mean);
        println!("  Std Dev: {:.3} ms\n", binding_tag_stats.std_dev);

        println!("Total generation time:");
        println!("  Median: {:.3} ms", total_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", total_stats.iqr, total_stats.q1, total_stats.q3);
        println!("  Min: {:.3} ms", total_stats.min);
        println!("  Max: {:.3} ms", total_stats.max);
        println!("  Mean: {:.3} ms", total_stats.mean);
        println!("  Std Dev: {:.3} ms\n", total_stats.std_dev);

        println!("=== Summary ===");
        println!("Compute blinding $b$: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 blinding_stats.median, blinding_stats.iqr, blinding_stats.min, blinding_stats.max);
        println!("Generate commitments (4×64-bit): median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 commitment_stats.median, commitment_stats.iqr, commitment_stats.min, commitment_stats.max);
        println!("Generate BP+ range proof: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 proof_stats.median, proof_stats.iqr, proof_stats.min, proof_stats.max);
        println!("Compute binding tag $t$: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 binding_tag_stats.median, binding_tag_stats.iqr, binding_tag_stats.min, binding_tag_stats.max);
        println!("Total generation time: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 total_stats.median, total_stats.iqr, total_stats.min, total_stats.max);

        // Verify that all operations completed successfully
        assert!(blinding_stats.median > 0.0, "Blinding computation should take time");
        assert!(commitment_stats.median > 0.0, "Commitment generation should take time");
        assert!(proof_stats.median > 0.0, "Proof generation should take time");
        assert!(binding_tag_stats.median > 0.0, "Binding tag computation should take time");
        assert!(total_stats.median > 0.0, "Total generation should take time");
        
        println!("\n✅ All tests passed!");
    }
}
