[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/rw-26ReD)
# Proving you did the work

In the previous assignment we explored how elliptic curve digital signatures work.
Digital signatures are the main authorization mechanism used in cryptocurrencies to avoid someone from spending your funds, they effectively define who owns what.
In particular, we saw that digital signatures are not infallible.
Even the most sophisticated mathematical constructions can be used in an insecure manner.

Another key aspect of security on cryptocurrency systems is determining the order in which transactions are to be considered.
Transactions in cryptocurrencies trigger a change in state maintained by the nodes in the network.
This is true for UTXO-based systems, like Bitcoin, that maintain a record of all the existing UTXOs; but also for balance-based systems, like Ethereum.
Proof of work is a fundamental piece of Nakamoto Consensus, a synchronization mechanism based on finding partial collisions of cryptographic hash functions that we explored in Assignment 1.

In this assignment we are going to explore what miners are doing in the Bitcoin network: selecting the transactions that will compose the next block, compute proof that those transactions were committed to the block, and grind hashes until they find a block with sufficient proof of work.

### Expected submissions

Your solutions should be in the form of text files in the `solutions` folder of your repo, containing the requested data in hex format.
The autograder will run the scripts in the `graders` folder to verify your answers.
You can use them to check your answers, but DO NOT MODIFY THE GRADER SCRIPTS.

These exercises are adaptions of the Bitcoin protocol, but we are not messing with endianness or double hashes.
**All cryptographic operations must use the (single) sha256 hash function**.
**All byte strings must be parsed and serialized as big endian**.

You can use any programming language you prefer, the graders will check only the final results you provide in text files.

Please commit your source code to the `implementation` folder so instructors can provide feedback on your approach.
The autograder is triggered when you push changes to the `main` branch.
Check its output on the `Actions` tab in the GitHub interface.

---

### Exercise 1: Transaction selection

Nodes maintain a list of valid unconfirmed transactions, called the *mempool*.
This is where miners look for transactions to include in blocks.

You are given the file `data/mempool.csv` that described a node's mempool with the format: `<txid>,<fee>,<weight>,<parent_txids>`.

- `txid` is the transaction identifier;
- `fee` is the absolute fee paid by the transaction;
- `weight` is the total "space" required by the transaction in the block;
- `parent_txids` is a list of txids of the transactions immediate parents, in the format `<txid1>;<txid2>;...`. Ancestors that are not immediate parents (e.g. parents of parents) and parent transactions that are already in the chain are not included in the list.

Your program should select transactions in this list to compose a block according to the following rules:

- The total weight of transactions in a block must not exceed 4,000,000 weight (4MvB).
- A transaction may appear in a block if, and only if, all of its ancestors appear *earlier* in the block.
- A transaction must not appear more than once in the block.
- A transaction may have zero, one, or many ancestors in the mempool. It may also have zero, one, or many children in the mempool.
- For this exercise, assume that there is no coinbase transaction.
- For this exercise, a block can't be empty.
- For this exercise, your block MUST include the transaction `4c50e3dad7f98bceb6441f96b23748dea84fbdb7cedd603441e6ea4a574d04a6`. 
- Your block should collect at least 50,000 sats in fees.

*Expected output*: a text file `solutions/exercise01.txt` with the list of selected txids, separated by newlines, which make a valid block, maximizing the fee to the miner.
Transactions must appear in order.
No transaction should appear unless its parents are included, no transaction should appear before its parents, and no transaction may appear more than once.

*Bonus for fun*:
Of course, you want to maximize the total amount of fees paid by the transactions included in your block, even though the autograder will not check for the amount paid in fees.
You are welcome to bribe yourself in the Discord server.
Let's see who can take the most out of this mempool!

Example output (not an actual solution):

```
9919d4db3c0c32cfc19c6ffa32496f18bf28607d941fd7b89a5710031c43f599
c63f430c09237dd7e43c31cb88512059416ef4c8fcd9134296ca6a919d185982
7270b580dec8b8ae6fdb28d8260de1932f8355823b5758b0e95d5ed8cf7d041c
03cd616cbb55a17f78bbe0c263f76c1007f9cd848f5c32a699b8805b9e436119
4c50e3dad7f98bceb6441f96b23748dea84fbdb7cedd603441e6ea4a574d04a6
```


---

### Exercise 2: Committing the selected transactions

For performance reasons, we don't hash the list of transactions that compose the block.
Instead, we build a block header that includes a commitment to those transactions; i.e., we include a (single) hash that can be used to efficiently prove that all the selected transactions were indeed included in the block.
We call this hash a *merkle root*.

Your program should compute the merkle root for the transactions provided in `data/ex02_txid_list.txt`, according to the following rules:

- Txids should be parsed as raw bytes (not pure strings).
- All hashes should be (single) `sha256`.
- Hashes should be combined in pairs by concatenating raw bytes, without any separators.
- If a hash has not a pair to combine, concatenate it with itself.

*Expected output*: a text file `solutions/exercise02.txt` with the merkle root of your block in the first line and proofs that the transaction `49ff8cccf1ca12179e9ae7a4760f550b5a18401b27e1e057604e27c3e10c08fb` was included in the block in the subsequent lines.

As an example, if your block was composed by the transactions on the example output of exercise 1 and you want to prove that transaction `4c50...` was included in the block, you would have the following output:

```
81dc159b17005ec03047b485a07901fe0762cbde9e8fdfd7fa0484d026394c20
03cd616cbb55a17f78bbe0c263f76c1007f9cd848f5c32a699b8805b9e436119
8cecc0d377b6f78e678c6cec8754577bd77567fadb6f5cd04e2a3058df6788d1
1343410f9bb7ba2de1e524e982036d43bf79a85dec5afcec45d6e34651835b9d
```

First line (`81dc...`) is the merkle root for those five transactions.
Next (`03cd...`) is the id of the transaction to the right of our target tx.
Next is the hash of `9919...` concatenated with `c63f...` that should be concatenated to the left to compose the next level of the tree.
Finally, `1343` is the part of the tree that was concatenated with itself two times in this example and that should be concatenated to the right of the previous result to reach the merkle root.

In other words:
- `81dc...` is the merkle root;
- `03cd...` is the level 0 sibling that gets hashed with the required txid `7270...`;
- `8cec...` is the level 1 sibling that gets hashed with above result;
- `1343...` is the level 2 sibling that gets hashed with the above result.


---

### Exercise 3: Grinding the proof of work

Now, let's build the block header and do the heavy computations.
You should be able to leverage Exercise 6 from Assignment 1 for this.

For this exercise, the block header will be composed by the following fields:

- `version`: 4 bytes. Should be greater than 1.
- `previous_block`: 32 bytes. Should be exactly `00000000d1145790a8694403d4063f323d499e655c83426834d4ce2f8dd4a2ee`.
- `merkle_root`: 32 bytes, as calculated in the previous exercise.
- `timestamp`: 4 bytes, unix time.
- `nonce`: 8 bytes.

1. The timestamp should be greater than `Jan 03 2009 16:15:05 UTC` and less than `Jan 12 2009 01:30:25 UTC`.
2. The header must be serialized by concatenating the fields in order, in hex.

The proof of work target is `0x1d00ffff`.
That means your block hash shoudlbe less than or equal to `00000000ffff0000000000000000000000000000000000000000000000000000`.

*NOTE*: That's the initial Bitcoin mainnet difficulty.
On a modern computer, you can mine this in a few minutes with a parallel implementation.
Imagine how much hardware Satoshi needed to mine this target in 2009.

*Expected output*: a text file `solutions/exercise03.txt` with a valid block header, in hex format.

Example output (with insufficient proof of work):
```
0000000200000000d1145790a8694403d4063f323d499e655c83426834d4ce2f8dd4a2eec0a692de10b69e2381a2856dcb0d0736dcd307bf25af7ce74831bf25793de626495f8f090000000000000000
```

*Bonus for fun*: Please report in the Discord server the time it took for your implementation to mine your block.
