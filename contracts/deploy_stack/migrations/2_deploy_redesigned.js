const ProductEscrow_Initializer = artifacts.require("ProductEscrow_Initializer");
const ProductFactory = artifacts.require("ProductFactory");

module.exports = async function (deployer) {
  console.log("Deploying redesigned contracts...");

  await deployer.deploy(ProductEscrow_Initializer);
  const implementation = await ProductEscrow_Initializer.deployed();
  console.log("Implementation:", implementation.address);

  await deployer.deploy(ProductFactory, implementation.address);
  const factory = await ProductFactory.deployed();
  console.log("Factory:", factory.address);

  const bondAmount = web3.utils.toWei("0.01", "ether");
  await factory.setBondAmount(bondAmount);
  console.log("Bond amount set to:", bondAmount, "wei (0.01 ETH)");
};
