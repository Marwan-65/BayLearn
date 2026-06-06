
#pragma once
#include "headers.h"
#include "process_table.c"
#include "RR_queue.h"

Memory *createMemoryBlock(int startAddress, int size)
{
    Memory *block = (Memory *)malloc(sizeof(Memory));
    block->startAddress = startAddress;
    block->size = size;
    block->processId = -1; // -1 indicates the block is free
    block->is_free = true;
    block->parent = NULL;
    block->left = NULL;
    block->right = NULL;
    return block;
}

Memory *smallestSuitable( Memory *node, int size)
{
    // If the node has both left and right children
    if (node->left && node->right)
    {
        // Recursively search in the left and right subtrees
        Memory *leftBlock = smallestSuitable(node->left, size);
        Memory *rightBlock = smallestSuitable(node->right, size);

        // If no suitable block is found in either subtree, return NULL
        if (leftBlock == NULL && rightBlock == NULL)
        {
            return NULL;
        }
        // If no suitable block is found in the left subtree, return the block from the right subtree
        if (leftBlock == NULL)
        {
            return rightBlock;
        }
        // If no suitable block is found in the right subtree, return the block from the left subtree
        if (rightBlock == NULL)
        {
            return leftBlock;
        }
        // If suitable blocks are found in both subtrees, return the smallest one
        if (leftBlock->size <= rightBlock->size)
        {
            return leftBlock;
        }
        else
        {
            return rightBlock;
        }
    }
    else
    {
        // If the node has no children (i.e., it's a leaf node), check if it's large enough and free
        if (node->size >= size && node->processId == -1)
        {
            return node;
        }
        else
        {
            return NULL;
        }
    }
}

Memory *occupyMemory(Memory *node, Process *process)
{
    if (node == NULL)
    {
        return NULL;
    }

    int size = process->memsize;
    int process_id = process->Id;

    Memory *temp = smallestSuitable(node, size);
    if (temp == NULL)
    {
        return NULL;
    }
    while (temp->size / 2 >= size)
    {
        temp->left = createMemoryBlock(temp->startAddress, temp->size / 2);
        temp->left->parent = temp;
        temp->right = createMemoryBlock(temp->startAddress + temp->size / 2, temp->size / 2);
        temp->right->parent = temp;
        temp = temp->left;
    }
    temp->processId = process_id;
    process->memoryBlock = temp;
    temp->is_free = false;
    Memory *parent = temp->parent;
    while (parent != NULL)
    {
        parent->is_free = false;
        parent = parent->parent;
    }
    return temp;
}

bool freeMemory(Memory *node, int process_id)
{
    if (node == NULL)
    {
        return false;
    }
    if (node->processId == process_id)
    {
        node->processId = -1;
        node->is_free = true;
        return true;
    }
    bool freedInLeft = freeMemory(node->left, process_id);
    bool freedInRight = freeMemory(node->right, process_id);
    if (node->left && node->right)
    {
        if (node->left->is_free && node->right->is_free)
        {
            node->is_free = true;
            free(node->left);
            free(node->right);
            node->left = NULL;
            node->right = NULL;
        }
    }
    return freedInLeft || freedInRight;
}

bool found(Memory *node, int id){
  if (node == NULL)
    {
        return false;
    }
    if (node->processId == id)
    {
        return true;
    }
    bool freedInLeft = found(node->left, id);
    bool freedInRight = found(node->right, id);
    return freedInLeft || freedInRight;
}