# A Conserved Recurrent Inhibitory Circuit in the Drosophila Antennal Lobe

**Dataset:** FAFB v783 — Female Adult Fly Brain  
**Circuit:** 38-neuron fully reciprocal clique of antennal lobe local interneurons (AL_R)  
**Also present in:** BANC v626 (female brain + VNC), MCNS v0.9 (male whole CNS)

---

## Visualizations

| Network Graph (top 50 connections by synapse count) | 3D Neuron Meshes in FAFB |
|:---:|:---:|
| *(see network_graph.png)* | *(see mesh_3d.png)* |

**[Open all 38 neurons in Codex 3D viewer →](https://codex.flywire.ai/app/view_3d?dataset=fafb&root_ids=720575940622338742,720575940619071005,720575940637136752,720575940637623780,720575940640541091,720575940640803200,720575940610161091,720575940628059978,720575940640415859,720575940621542747,720575940621585279,720575940612347571,720575940646576436,720575940605758142,720575940648633988,720575940612637554,720575940629792732,720575940622650879,720575940660217729,720575940613804259,720575940630225403,720575940616758322,720575940616908177,720575940624832743,720575940623137997,720575940617299131,720575940614956072,720575940622726271,720575940625584484,720575940618112310,720575940625585508,720575940615708482,720575940623792648,720575940631603281,720575940626342174,720575940616197819,720575940631704716,720575940624435128)**

The network graph shows two natural clusters — an lLN2 subtype group (upper, with stronger individual connections, up to 618 synapses per pair) and an lLN1_bc group (lower, more evenly distributed). The two projection neurons, DM1_lPN and DP1m_adPN, appear as peripheral nodes receiving from the lLN2 core. The 3D mesh view shows all 38 neurons as a dense mass co-localized in the right antennal lobe, with the two projection neurons extending axons outward toward the mushroom body.

---

## What the Circuit Is

The 38 matched neurons in FAFB are all right-hemisphere, central, intrinsic neurons confined to the antennal lobe (AL_R). Thirty-six are Antennal Lobe Local Neurons (ALLNs) — multiglomerular inhibitory interneurons that innervate many glomeruli simultaneously. Thirty-five of those share the ALl1_dorsal developmental hemilineage, meaning they were born from the same neuroblast lineage. The remaining two are uniglomerular projection neurons (DM1_lPN and DP1m_adPN) that project to the mushroom body calyx, representing the circuit's output pathway.

The dominant cell types are lLN1_bc (16 neurons) and various lLN2 subtypes (lLN2X12, lLN2X04, lLN2F_a, lLN2X11, lLN2T_c, lLN2X05 — 17 neurons combined). The lLN1 and lLN2 classes are the two main multiglomerular inhibitory populations in the Drosophila antennal lobe, known to span many or all glomeruli and coordinate activity across odor channels [1].

All 1,406 possible directed edges are present, and all 703 unordered pairs are bidirectional — every neuron in the circuit connects to every other in both directions. The 86,275 internal synapses land almost entirely in AL_R (99.98%). The mean connection strength is 61.4 synapses per directed pair, with the strongest single connection at 618 synapses (lLN2T_c → v2LN30).

The synapse-weighted neurotransmitter profile of the internal connections is cholinergic-serotonergic: ACH 38.4%, SER 34.2%, DA 18.6%, GABA 8.8%. Note that per-neuron NT labels from Codex are ambiguous for 23 of the 38 neurons because the classifier confidence fell below threshold — a documented limitation for this cell class [2].

---

## What the Circuit Does

The antennal lobe is the fly's first olfactory processing center, analogous to the vertebrate olfactory bulb. Olfactory receptor neurons (ORNs) detect odors and pass signals to projection neurons (PNs), which relay those signals to the mushroom body and lateral horn for learning and behavior. Local interneurons (LNs) sit in the middle of this pathway and regulate how strongly PNs respond.

The key function of multiglomerular LNs is **lateral inhibition**: when one glomerulus is strongly activated by an odor, the LNs spread that signal across many other glomeruli and suppress their output. This keeps the PN responses calibrated to the total odor intensity rather than saturating on strong odors — a process called **divisive normalization** [3]. Essentially, the LN network acts as a volume knob: it prevents any one odor channel from dominating and keeps the system sensitive across a wide range of odor concentrations.

The all-to-all bidirectional topology of the 38-neuron clique is the structural prerequisite for this computation. When two neurons mutually inhibit each other, their individual activity levels become coupled — each is partially suppressed by the other's response. With all 703 pairs in the circuit doing this simultaneously, the result is a globally coordinated suppression that normalizes activity across all participating glomeruli. LN-LN reciprocal connections in the antennal lobe have been specifically implicated in bistable gain control: the recurrent inhibitory network can switch between a mode that suppresses global activity (when odors are strong) and a mode that allows weak signals through (when odors are faint) [4].

The two embedded projection neurons (DM1_lPN and DP1m_adPN) are not passive bystanders. They are among the strongest drivers in the circuit — DM1_lPN sends 408 synapses to lLN2T_c and DP1m_adPN sends 305 synapses to the same target. Their presence inside the recurrent clique suggests the circuit also incorporates direct feedback from the output layer, not just interneuron-to-interneuron inhibition. The circuit sits upstream of the mushroom body, with 9,701 synapses flowing from the clique members to KCab Kenyon cells and 4,881 to KCg-m Kenyon cells — putting the recurrent LN network directly in the pipeline for olfactory learning and memory.

---

## Why It Appears in Three Connectomes

The same 38-neuron circuit, with identical directed topology, was found in three independent EM reconstructions: FAFB (female brain), BANC (female brain and ventral nerve cord), and MCNS (male whole CNS). These span both sexes and multiple body regions.

The antennal lobe is already known to be broadly stereotyped across individuals [5]. Finding the identical graph structure of a 38-neuron fully reciprocal inhibitory clique across male and female flies suggests this specific circuit is not just an approximate anatomical similarity — it is an exactly reproducible wiring pattern. The antennal lobe is one of the two highest-reciprocity neuropils in the entire FlyWire connectome, and its neuropil-specific highly reciprocal neurons are predominantly inhibitory ALLNs [6]. The 38-neuron clique is a concrete example of this class of structure, now confirmed in three animals.

---

## Hypothesis

The 38-neuron reciprocal ALLN clique represents a conserved gain control module in the right antennal lobe. I hypothesize that this circuit sets the dynamic range of olfactory processing in the right hemisphere by implementing divisive normalization across the glomeruli it innervates. Because the circuit is structurally identical across male and female flies, its function is unlikely to be sex-specific — instead, it may reflect a general-purpose computational unit for odor intensity normalization that is developmentally hardwired from the ALl1_dorsal lineage.

A direct test: optogenetically silencing the 36 ALLN members of this circuit while recording from right-hemisphere projection neurons should specifically impair gain normalization — PN responses should saturate at lower odor concentrations and lose concentration-invariant identity coding — without equivalently affecting left-hemisphere PNs.

---

## References

[1] Chou, Y.H. et al. (2010). Diversity and wiring variability of olfactory local interneurons in the Drosophila antennal lobe. *Nature Neuroscience* 13, 439–449. https://doi.org/10.1038/nn.2489

[2] Eckstein, N. et al. (2024). Neurotransmitter classification from electron microscopy images at synaptic sites in Drosophila melanogaster. *Cell* 187, 2574–2594. https://doi.org/10.1016/j.cell.2024.03.016

[3] Olsen, S.R., Bhandawat, V. & Wilson, R.I. (2010). Divisive normalization in olfactory population codes. *Neuron* 66, 287–299. https://doi.org/10.1016/j.neuron.2010.04.009

[4] Berck, M.E. et al. (2016). The wiring diagram of a glomerular olfactory system. *eLife* 5, e14859. https://doi.org/10.7554/eLife.14859

[5] Schlegel, P. et al. (2024). Whole-brain annotation and multi-connectome cell typing quantifies circuit stereotypy in Drosophila. *Nature* 634, 139–152. https://doi.org/10.1038/s41586-024-07686-5

[6] Lin, A. et al. (2024). Network statistics of the whole-brain connectome of Drosophila. *Nature* 634, 153–165. https://doi.org/10.1038/s41586-024-07968-y
