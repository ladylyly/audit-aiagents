// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./ProductEscrow_Initializer.sol";

// Interface for calling ProductEscrow functions without casting issues
interface IProductEscrowOwner {
    function owner() external view returns (address payable);
}

// Standardized custom errors for gas efficiency and consistency
error InvalidImplementationAddress();
error FactoryIsPaused();
error BondAmountNotSet();
error BondAmountZero();
error IncorrectBondAmount();

contract ProductFactory is Ownable {
    using Clones for address;

    event ProductCreated(address indexed product, address indexed seller, uint256 indexed productId, bytes32 priceCommitment, uint256 bondAmount);
    event ImplementationUpdated(address indexed oldImpl, address indexed newImpl);
    event FactoryPaused(address indexed by);
    event FactoryUnpaused(address indexed by);
    event BondAmountUpdated(uint256 newAmount);

    // Packed storage for gas optimization
    address public implementation;
    uint256 public productCount;
    bool public isPaused; // Lightweight pause mechanism (factory-level only)
    uint256 public bondAmount; // Configurable bond amount for seller and transporter

    // Paged getter for dev convenience (optional, not main indexing)
    address[] public products;

    constructor(address _impl) Ownable(msg.sender) {
        if (_impl == address(0)) revert InvalidImplementationAddress();
        implementation = _impl;
        emit ImplementationUpdated(address(0), _impl);
    }

    modifier whenNotPaused() {
        if (isPaused) revert FactoryIsPaused();
        _;
    }

    // Alias for the suggested function name
    function setImplementation(address _impl) external onlyOwner {
        if (_impl == address(0)) revert InvalidImplementationAddress();
        address oldImpl = implementation;
        implementation = _impl;
        emit ImplementationUpdated(oldImpl, _impl);
    }

    /// @notice Set the required bond amount for seller and transporter.
    /// @param _amount Bond amount in wei (must be > 0)
    function setBondAmount(uint256 _amount) external onlyOwner {
        if (_amount == 0) revert BondAmountZero();
        bondAmount = _amount;
        emit BondAmountUpdated(_amount);
    }

    function pause() external onlyOwner {
        isPaused = true;
        emit FactoryPaused(msg.sender);
    }

    function unpause() external onlyOwner {
        isPaused = false;
        emit FactoryUnpaused(msg.sender);
    }

    /// @notice Create a new product escrow. Seller sends bond as msg.value.
    /// @param name Product name
    /// @param priceCommitment Confidential price commitment (keccak256 hash)
    /// @return product Address of the newly created escrow clone
    function createProduct(string memory name, bytes32 priceCommitment)
        external
        payable
        whenNotPaused
        returns (address product)
    {
        if (bondAmount == 0) revert BondAmountNotSet();
        if (msg.value != bondAmount) revert IncorrectBondAmount();

        product = implementation.clone();

        // Use unchecked for safe increment
        unchecked {
            productCount++;
        }

        // Initialize the clone and forward seller bond as msg.value
        ProductEscrow_Initializer(payable(product)).initialize{value: msg.value}(
            productCount,
            name,
            priceCommitment,
            msg.sender,
            bondAmount,
            address(this)
        );

        // Store for optional paged access (dev convenience)
        products.push(product);

        emit ProductCreated(product, msg.sender, productCount, priceCommitment, bondAmount);
    }

    /// @notice Create a new product escrow at a deterministic address. Seller sends bond as msg.value.
    /// @param name Product name
    /// @param priceCommitment Confidential price commitment (keccak256 hash)
    /// @param salt Salt for deterministic clone address
    /// @return product Address of the newly created escrow clone
    function createProductDeterministic(
        string memory name,
        bytes32 priceCommitment,
        bytes32 salt
    )
        external
        payable
        whenNotPaused
        returns (address product)
    {
        if (bondAmount == 0) revert BondAmountNotSet();
        if (msg.value != bondAmount) revert IncorrectBondAmount();

        product = implementation.cloneDeterministic(salt);

        // Use unchecked for safe increment
        unchecked {
            productCount++;
        }

        // Initialize the clone and forward seller bond as msg.value
        ProductEscrow_Initializer(payable(product)).initialize{value: msg.value}(
            productCount,
            name,
            priceCommitment,
            msg.sender,
            bondAmount,
            address(this)
        );

        // Store for optional paged access (dev convenience)
        products.push(product);

        emit ProductCreated(product, msg.sender, productCount, priceCommitment, bondAmount);
    }

    function predictProductAddress(bytes32 salt) public view returns (address) {
        return Clones.predictDeterministicAddress(implementation, salt, address(this));
    }

    // Optional paged getter for dev convenience (not main indexing)
    // Optimized to avoid unbounded loops in write operations
    function getProductsRange(uint256 start, uint256 count) public view returns (address[] memory) {
        require(start < products.length, "Start index out of bounds");
        uint256 end = start + count;
        if (end > products.length) {
            end = products.length;
        }

        uint256 resultLength = end - start;
        address[] memory result = new address[](resultLength);

        // Use unchecked for safe loop operations
        unchecked {
            for (uint256 i = start; i < end; i++) {
                result[i - start] = products[i];
            }
        }

        return result;
    }

    // Gas-efficient getter for total products (alternative to array.length)
    function getProductCount() public view returns (uint256) {
        return productCount;
    }

    // Gas-efficient getter for all products (alternative to array access)
    function getProducts() public view returns (address[] memory) {
        return products;
    }

    // Get products by seller (fixed implementation)
    function getProductsBySeller(address _seller) public view returns (address[] memory) {
        uint256 count = 0;

        // First pass: count products by this seller
        for (uint256 i = 0; i < products.length; i++) {
            try IProductEscrowOwner(products[i]).owner() returns (address payable _owner) {
                if (_owner == _seller) {
                    count++;
                }
            } catch {
                // Skip if product is not properly initialized
                continue;
            }
        }

        // Second pass: collect product addresses
        address[] memory sellerProducts = new address[](count);
        uint256 index = 0;

        for (uint256 i = 0; i < products.length; i++) {
            try IProductEscrowOwner(products[i]).owner() returns (address payable _owner) {
                if (_owner == _seller && index < count) {
                    sellerProducts[index] = products[i];
                    index++;
                }
            } catch {
                continue;
            }
        }

        return sellerProducts;
    }

    // Explicitly reject unexpected ETH
    receive() external payable {
        revert("Factory does not accept ETH");
    }

    fallback() external payable {
        revert("Factory does not accept ETH");
    }
}
