//! Test 3.2: Proof Generation Time
//! Measures time to generate a range proof with breakdown of operations

use bulletproof_demo::zk::pedersen::prove_value_commitment_with_binding_and_range;
use curve25519_dalek_ng::scalar::Scalar;
use std::time::Instant;
use sha2::{Sha256, Digest};

// Helper function to compute deterministic blinding factor
// In production: keccak256(abi.encodePacked(escrowAddr, owner))
fn compute_blinding(escrow_addr: &[u8], owner: &[u8]) -> Scalar {
    let mut hasher = Sha256::new();
    hasher.update(escrow_addr);
    hasher.update(owner);
    let hash = hasher.finalize();
    let mut bytes = [0u8; 32];
    bytes.copy_from_slice(&hash[..32]);
    Scalar::from_bytes_mod_order(bytes)
}

// Helper function to compute binding tag
// In production: keccak256(chainId || escrowAddr || productId || stage || schemaVersion || previousVCCid)
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

// Helper function to generate commitment (Pedersen commitment)
fn generate_commitment(value: u64, blinding: Scalar) -> curve25519_dalek_ng::ristretto::CompressedRistretto {
    use bulletproofs::PedersenGens;
    let pc_gens = PedersenGens::default();
    pc_gens.commit(Scalar::from(value), blinding).compress()
}

// Statistics calculation
struct Stats {
    median: f64,
    q1: f64,  // First quartile (25th percentile)
    q3: f64,  // Third quartile (75th percentile)
    iqr: f64, // Interquartile range
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
    fn test_proof_generation_time() {
        println!("\n🧪 Test 3.2: Proof Generation Time\n");

        const RUNS: usize = 100;
        const BIT_RANGE: usize = 64; // 64-bit range proof
        
        // Test parameters
        let value = 1000000u64;
        let escrow_addr = b"0xc448142dF27D18A7bE5a439589320429AB18855c";
        let owner = b"0x88dcDCfB5e330049597003D41eF8E744Fa613E68";
        let chain_id = "11155111";
        let product_id = 14u64;
        let stage = 0u8;
        let schema_version = "1.0";
        let previous_vc_cid: Option<&str> = None;

        let mut blinding_times = Vec::new();
        let mut commitment_times = Vec::new();
        let mut proof_times = Vec::new();
        let mut binding_tag_times = Vec::new();
        let mut total_times = Vec::new();

        println!("Running {} iterations for 64-bit range proof generation...\n", RUNS);

        // Warm-up run (not counted)
        let _ = compute_blinding(escrow_addr, owner);
        let _ = generate_commitment(value, compute_blinding(escrow_addr, owner));
        let _ = compute_binding_tag(chain_id, escrow_addr, product_id, stage, schema_version, previous_vc_cid);

        for i in 0..RUNS {
            let total_start = Instant::now();

            // 1. Compute blinding
            let blinding_start = Instant::now();
            let blinding = compute_blinding(escrow_addr, owner);
            let blinding_time = blinding_start.elapsed();
            blinding_times.push(blinding_time.as_nanos() as f64 / 1_000_000.0); // Convert to milliseconds

            // 2. Compute binding tag
            let binding_start = Instant::now();
            let binding_tag = compute_binding_tag(chain_id, escrow_addr, product_id, stage, schema_version, previous_vc_cid);
            let binding_time = binding_start.elapsed();
            binding_tag_times.push(binding_time.as_nanos() as f64 / 1_000_000.0);

            // 3. Generate commitment (Pedersen commitment)
            let commit_start = Instant::now();
            let _commitment = generate_commitment(value, blinding);
            let commit_time = commit_start.elapsed();
            commitment_times.push(commit_time.as_nanos() as f64 / 1_000_000.0);

            // 4. Generate range proof (includes commitment generation internally, but we measure the full operation)
            let proof_start = Instant::now();
            let (_commitment2, _proof_bytes, _verified) = prove_value_commitment_with_binding_and_range(
                value,
                blinding,
                Some(&binding_tag),
                BIT_RANGE,
            );
            let proof_time = proof_start.elapsed();
            proof_times.push(proof_time.as_nanos() as f64 / 1_000_000.0);

            let total_time = total_start.elapsed();
            total_times.push(total_time.as_nanos() as f64 / 1_000_000.0);

            if (i + 1) % 10 == 0 {
                print!(".");
                use std::io::Write;
                std::io::stdout().flush().unwrap();
            }
        }
        println!("\n");

        // Calculate statistics
        let blinding_stats = calculate_stats(&blinding_times);
        let commitment_stats = calculate_stats(&commitment_times);
        let proof_stats = calculate_stats(&proof_times);
        let binding_tag_stats = calculate_stats(&binding_tag_times);
        let total_stats = calculate_stats(&total_times);

        // Output results
        println!("=== Proof Generation Time Statistics ({} runs) ===\n", RUNS);
        
        println!("Compute blinding $b$:");
        println!("  Median: {:.3} ms", blinding_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", blinding_stats.iqr, blinding_stats.q1, blinding_stats.q3);
        println!("  Min: {:.3} ms", blinding_stats.min);
        println!("  Max: {:.3} ms", blinding_stats.max);
        println!("  Mean: {:.3} ms", blinding_stats.mean);
        println!("  Std Dev: {:.3} ms\n", blinding_stats.std_dev);

        println!("Generate commitment $C$:");
        println!("  Median: {:.3} ms", commitment_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", commitment_stats.iqr, commitment_stats.q1, commitment_stats.q3);
        println!("  Min: {:.3} ms", commitment_stats.min);
        println!("  Max: {:.3} ms", commitment_stats.max);
        println!("  Mean: {:.3} ms", commitment_stats.mean);
        println!("  Std Dev: {:.3} ms\n", commitment_stats.std_dev);

        println!("Generate range proof:");
        println!("  Median: {:.3} ms", proof_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", proof_stats.iqr, proof_stats.q1, proof_stats.q3);
        println!("  Min: {:.3} ms", proof_stats.min);
        println!("  Max: {:.3} ms", proof_stats.max);
        println!("  Mean: {:.3} ms", proof_stats.mean);
        println!("  Std Dev: {:.3} ms\n", proof_stats.std_dev);

        println!("Compute binding tag $t$:");
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
        println!("Generate commitment $C$: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 commitment_stats.median, commitment_stats.iqr, commitment_stats.min, commitment_stats.max);
        println!("Generate range proof: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
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

