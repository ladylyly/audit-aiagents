//! Test 3.3: Proof Verification Time
//! Measures time to verify a range proof with breakdown of operations

use bulletproof_demo::zk::pedersen::{
    prove_value_commitment_with_binding_and_range,
    verify_value_commitment_with_binding,
};
use curve25519_dalek_ng::scalar::Scalar;
use std::time::Instant;
use sha2::{Sha256, Digest};

// Helper function to compute deterministic blinding factor
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
    fn test_proof_verification_time() {
        println!("\n🧪 Test 3.3: Proof Verification Time\n");

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

        // Generate a valid proof once (before timing verification)
        println!("Generating test proof...");
        let blinding = compute_blinding(escrow_addr, owner);
        let binding_tag = compute_binding_tag(chain_id, escrow_addr, product_id, stage, schema_version, previous_vc_cid);
        
        let (commitment, proof_bytes, verified_gen) = prove_value_commitment_with_binding_and_range(
            value,
            blinding,
            Some(&binding_tag),
            BIT_RANGE,
        );
        
        assert!(verified_gen, "Generated proof should verify");
        println!("Proof generated successfully.\n");

        let mut setup_times = Vec::new();
        let mut verify_times = Vec::new();
        let mut total_times = Vec::new();

        println!("Running {} verification iterations...\n", RUNS);

        // Warm-up run (not counted)
        let _ = verify_value_commitment_with_binding(
            commitment,
            proof_bytes.clone(),
            Some(&binding_tag),
        );

        for i in 0..RUNS {
            let total_start = Instant::now();

            // Setup public inputs (commitment C and binding tag t)
            // Setup involves: creating generators, creating transcript, adding binding tag, parsing proof
            let setup_start = Instant::now();
            use bulletproofs::{BulletproofGens, PedersenGens};
            use bulletproofs::RangeProof;
            use merlin::Transcript;
            
            let pc_gens = PedersenGens::default();
            let bp_gens = BulletproofGens::new(BIT_RANGE, 1);
            let mut transcript = Transcript::new(b"ValueRangeProof");
            transcript.append_message(b"bind", &binding_tag);
            
            // Parse proof from bytes (part of setup)
            let proof = match RangeProof::from_bytes(&proof_bytes) {
                Ok(p) => p,
                Err(_) => {
                    panic!("Failed to parse proof");
                }
            };
            let setup_time = setup_start.elapsed();
            setup_times.push(setup_time.as_nanos() as f64 / 1_000_000.0);

            // Verify proof (the actual RangeProof::verify_single operation)
            let verify_start = Instant::now();
            let verified = RangeProof::verify_single(
                &proof,
                &bp_gens,
                &pc_gens,
                &mut transcript,
                &commitment,
                BIT_RANGE,
            ).is_ok();
            let verify_time = verify_start.elapsed();
            verify_times.push(verify_time.as_nanos() as f64 / 1_000_000.0);

            let total_time = total_start.elapsed();
            total_times.push(total_time.as_nanos() as f64 / 1_000_000.0);

            assert!(verified, "Proof should verify correctly");

            if (i + 1) % 10 == 0 {
                print!(".");
                use std::io::Write;
                std::io::stdout().flush().unwrap();
            }
        }
        println!("\n");

        // Calculate statistics
        let setup_stats = calculate_stats(&setup_times);
        let verify_stats = calculate_stats(&verify_times);
        let total_stats = calculate_stats(&total_times);

        // Output results
        println!("=== Proof Verification Time Statistics ({} runs) ===\n", RUNS);
        
        println!("Setup public inputs $(C,t)$:");
        println!("  Median: {:.3} ms", setup_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", setup_stats.iqr, setup_stats.q1, setup_stats.q3);
        println!("  Min: {:.3} ms", setup_stats.min);
        println!("  Max: {:.3} ms", setup_stats.max);
        println!("  Mean: {:.3} ms", setup_stats.mean);
        println!("  Std Dev: {:.3} ms\n", setup_stats.std_dev);

        println!("Verify range proof:");
        println!("  Median: {:.3} ms", verify_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", verify_stats.iqr, verify_stats.q1, verify_stats.q3);
        println!("  Min: {:.3} ms", verify_stats.min);
        println!("  Max: {:.3} ms", verify_stats.max);
        println!("  Mean: {:.3} ms", verify_stats.mean);
        println!("  Std Dev: {:.3} ms\n", verify_stats.std_dev);

        println!("Total verification time:");
        println!("  Median: {:.3} ms", total_stats.median);
        println!("  IQR: {:.3} ms (Q1: {:.3}, Q3: {:.3})", total_stats.iqr, total_stats.q1, total_stats.q3);
        println!("  Min: {:.3} ms", total_stats.min);
        println!("  Max: {:.3} ms", total_stats.max);
        println!("  Mean: {:.3} ms", total_stats.mean);
        println!("  Std Dev: {:.3} ms\n", total_stats.std_dev);

        println!("=== Summary ===");
        println!("Setup public inputs $(C,t)$: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 setup_stats.median, setup_stats.iqr, setup_stats.min, setup_stats.max);
        println!("Verify range proof: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 verify_stats.median, verify_stats.iqr, verify_stats.min, verify_stats.max);
        println!("Total verification time: median={:.3} ms, IQR={:.3} ms, min={:.3} ms, max={:.3} ms", 
                 total_stats.median, total_stats.iqr, total_stats.min, total_stats.max);

        // Verify that all operations completed successfully
        assert!(setup_stats.median >= 0.0, "Setup should take time");
        assert!(verify_stats.median > 0.0, "Verification should take time");
        assert!(total_stats.median > 0.0, "Total verification should take time");
        
        println!("\n✅ All tests passed!");
    }
}

