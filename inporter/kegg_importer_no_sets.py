import os

from os import listdir
from os.path import isfile, join

from Bio.KEGG.REST import kegg_list, kegg_get
from Bio.KEGG.KGML import KGML_parser

import argparse
from import_utils import GraphImporter

parser = argparse.ArgumentParser(description='KEGG Importer')
parser.add_argument('--db', default='http://192.168.56.1:7474/db/data/')
parser.add_argument('--data_dir', '-d', default='/vagrant_data/kegg/',
                    help='data directory')
parser.add_argument('--clear', action='store_true', help='clear the graph')
parser.add_argument('--commitEvery', type=int, default=100, help='commit every x steps')
args = parser.parse_args()

importer = GraphImporter(args.db, args.commitEvery)
if args.clear or True:
  importer.delete_all()

if not os.path.exists(args.data_dir):
  os.makedirs(args.data_dir)

files = [f for f in listdir(args.data_dir) if isfile(join(args.data_dir, f))]

if len(files) == 0:
  # download kgml files
  res = kegg_list('pathway', 'hsa').read()
  items = res.split('\n')
  for item in items[:len(items) - 1]:
    pathway_id = item[5:13]
    if pathway_id != 'hsa01100':
      print('fetching ' + pathway_id)
      kgml = kegg_get(pathway_id, 'kgml').read()
      with open(args.data_dir + pathway_id + '.kgml', 'w') as text_file:
        text_file.write(kgml)

  files = [f for f in listdir(args.data_dir) if isfile(join(args.data_dir, f))]

# Maps from the extracted node id (e.g. EGFR) to the Node Object
nodes = set()
# Map to prevent multiple creation of edges between two nodes uses concatenated node ids as keys (e.g. EGFR_C00010)
# edgeDict = dict()

# batch = WriteBatch(graph)

for filename in files:
  url = args.data_dir + filename
  print ('Loading file ' + url)

  currentNodes = set()
  currentEdges = dict()

  with open(url) as f:
    pathway = KGML_parser.read(f, 'r')
    # Maps from the reaction id (e.g. rn:R05134) to the Node Objects that are part of this reaction
    reactionToNode = dict()
    # Maps from the internal pathway id (e.g. 23) to the compound id (e.g. C00010)
    compoundDict = dict()

    for gene in pathway.genes:
      for geneName in gene.name.split(' '):
        gene_id = geneName[4:]
        if gene_id not in nodes:
          importer.add_node(['_Network_Node', 'Gene'], gene_id, {'name': gene_id, 'idType': 'ENTREZ'})

          # node = Node('NETWORK_NODE', 'Gene', id=name, idType='GENE_SYMBOL', name=name)

          # n = batch.create(node)
          nodes.add(gene_id)
        genesInReaction = set()
        if gene.reaction not in reactionToNode:
          reactionToNode[gene.reaction] = genesInReaction
        else:
          genesInReaction = reactionToNode[gene.reaction]
        genesInReaction.add(gene_id)
        currentNodes.add(gene_id)

    # print(reactionToNode)

    for compound in pathway.compounds:
      for compoundName in compound.name.split(' '):
        compound_id = compoundName[4:]
        if compound_id not in nodes:
          importer.add_node(['_Network_Node', 'Compound'], compound_id,
                            {'name': compound_id, 'idType': 'KEGG_COMPOUND'})

          # node = Node('NETWORK_NODE', 'Compound', id=name, idType='KEGG_COMPOUND', name=name)
          # n = batch.create(node)
          nodes.add(compound_id)
        if compound.id not in compoundDict:
          compoundDict[compound.id] = compound_id
        currentNodes.add(compound_id)

    importer.done_nodes()

    for reaction in pathway.reactions:
      if reaction.name in reactionToNode:
        gene_ids = reactionToNode[reaction.name]
        for gene_id in gene_ids:
          for substrate in reaction.substrates:
            substrate_id = substrate.name[4:]
            if substrate_id in nodes:
              importer.add_edge('Edge', substrate_id, gene_id, {'_isNetworkEdge': True})
              currentEdges[substrate_id + '_' + gene_id] = {'source': substrate_id, 'target': gene_id}

              # create_pathway_edge(edgeDict, substrateNode, node)
              if reaction.type == 'reversible':
                importer.add_edge('Edge', gene_id, substrate_id, {'_isNetworkEdge': True})
                currentEdges[gene_id + '_' + substrate_id] = {'source': gene_id, 'target': substrate_id}
                # create_pathway_edge(edgeDict, node, substrateNode)

          for product in reaction.products:
            product_id = substrate.name[4:]
            if product_id in nodes:
              importer.add_edge('Edge', gene_id, product_id, {'_isNetworkEdge': True})
              currentEdges[gene_id + '_' + product_id] = {'source': gene_id, 'target': product_id}

              # create_pathway_edge(edgeDict, node, productNode)

              if reaction.type == 'reversible':
                importer.add_edge('Edge', product_id, gene_id, {'_isNetworkEdge': True})
                currentEdges[product_id + '_' + gene_id] = {'source': product_id, 'target': gene_id}

                # create_pathway_edge(edgeDict, productNode, node)

    for relation in pathway.relations:
      isCompound = False
      compounds = []

      for subtype in relation.subtypes:
        if subtype[0] in ('compound', 'hidden compound'):
          if subtype[1] in compoundDict:
            compoundName = compoundDict[subtype[1]]
            if compoundName in nodes:
              # compoundNode = nodeDict[compoundName]
              isCompound = True
              compounds.append(compoundName)

      for geneName in relation.entry1.name.split(' '):
        source_gene_id = geneName[4:]
        if source_gene_id in nodes:
          for g in relation.entry2.name.split(' '):
            target_gene_id = g[4:]
            if target_gene_id in nodes:
              if isCompound:
                for compoundNode in compounds:
                  importer.add_edge('Edge', source_gene_id, compoundNode, {'_isNetworkEdge': True})
                  currentEdges[source_gene_id + '_' + compoundNode] = {'source': source_gene_id, 'target': compoundNode}

                  importer.add_edge('Edge', compoundNode, target_gene_id, {'_isNetworkEdge': True})
                  currentEdges[compoundNode + '_' + target_gene_id] = {'source': compoundNode, 'target': target_gene_id}

                  # create_pathway_edge(edgeDict, sourceNode, compoundNode)
                  # create_pathway_edge(edgeDict, compoundNode, targetNode)
              else:
                importer.add_edge('Edge', source_gene_id, target_gene_id, {'_isNetworkEdge': True})
                currentEdges[source_gene_id + '_' + target_gene_id] = {'source': source_gene_id,
                                                                       'target': target_gene_id}

                # create_pathway_edge(edgeDict, sourceNode, targetNode)

  importer.add_node(['_Set_Node', 'Pathway'], pathway.name[5:],
                    {'name': pathway.title, 'idType': 'KEGG_PATHWAY', 'url': pathway.link, 'imageUrl': pathway.image})

  nodes.add(pathway.name)

  for node in currentNodes:
    importer.add_node(['_Network_Node'], node, {'pathways': [pathway.name[5:]]})
    importer.add_edge('ConsistsOf', pathway.name[5:], node, {}, 'Pathway')

  for edge in currentEdges.values():
    importer.add_edge('Edge', edge['source'], edge['target'], {'pathways': [pathway.name[5:]], '_isSetEdge': True})

  importer.done_nodes()

importer.finish()